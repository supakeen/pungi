# -*- coding: utf-8 -*-

import copy
import json
import os
from kobo import shortcuts
from kobo.threads import ThreadPool, WorkerThread
from collections import OrderedDict

from pungi.runroot import Runroot
from .base import ConfigGuardedPhase
from .. import util
from ..util import get_repo_dicts, translate_path
from ..wrappers import scm


class OSTreeContainerPhase(ConfigGuardedPhase):
    name = "ostree_container"

    def __init__(self, compose, pkgset_phase=None):
        super(OSTreeContainerPhase, self).__init__(compose)
        self.pool = ThreadPool(logger=self.compose._logger)
        self.pkgset_phase = pkgset_phase

    def get_repos(self):
        return [
            translate_path(
                self.compose,
                self.compose.paths.work.pkgset_repo(pkgset.name, "$basearch"),
            )
            for pkgset in self.pkgset_phase.package_sets
        ]

    def _enqueue(self, variant, arch, conf):
        self.pool.add(OSTreeContainerThread(self.pool, self.get_repos()))
        self.pool.queue_put((self.compose, variant, arch, conf))

    def run(self):
        if isinstance(self.compose.conf.get(self.name), dict):
            for variant in self.compose.get_variants():
                for conf in self.get_config_block(variant):
                    for arch in conf.get("arches", []) or variant.arches:
                        self._enqueue(variant, arch, conf)
        else:
            # Legacy code path to support original configuration.
            for variant in self.compose.get_variants():
                for arch in variant.arches:
                    for conf in self.get_config_block(variant, arch):
                        self._enqueue(variant, arch, conf)

        self.pool.start()


class OSTreeContainerThread(WorkerThread):
    def __init__(self, pool, repos):
        super(OSTreeContainerThread, self).__init__(pool)
        self.repos = repos

    def process(self, item, num):
        compose, variant, arch, config = item
        self.num = num
        failable_arches = config.get("failable", [])
        with util.failable(
            compose,
            util.can_arch_fail(failable_arches, arch),
            variant,
            arch,
            "ostree-container",
        ):
            self.worker(compose, variant, arch, config)

    def worker(self, compose, variant, arch, config):
        msg = "OSTree phase for variant %s, arch %s" % (variant.uid, arch)
        self.pool.log_info("[BEGIN] %s" % msg)
        workdir = compose.paths.work.topdir("ostree-%d" % self.num)
        self.logdir = compose.paths.log.topdir(
            "%s/%s/ostree-container-%d" % (arch, variant.uid, self.num)
        )
        repodir = os.path.join(workdir, "config_repo")
        self._clone_repo(
            compose,
            repodir,
            config["config_url"],
            config.get("config_branch", "main"),
        )

        repos = shortcuts.force_list(config["repo"]) + self.repos
        repos = get_repo_dicts(repos, logger=self.pool)

        # copy the original config and update before save to a json file
        new_config = copy.copy(config)

        # repos in configuration can have repo url set to variant UID,
        # update it to have the actual url that we just translated.
        new_config.update({"repo": repos})

        # remove unnecessary (for 'pungi-make-ostree container' script ) elements
        # from config, it doesn't hurt to have them, however remove them can
        # reduce confusion
        for k in [
            "treefile",
            "config_url",
            "config_branch",
            "failable",
            "version",
        ]:
            new_config.pop(k, None)

        # write a json file to save the configuration, so 'pungi-make-ostree tree'
        # can take use of it
        extra_config_file = os.path.join(workdir, "extra_config.json")
        with open(extra_config_file, "w") as f:
            json.dump(new_config, f, indent=4)

        self._run_ostree_container_cmd(
            compose, variant, arch, config, repodir, extra_config_file=extra_config_file
        )

        if compose.notifier:
            # 'pungi-make-ostree container' writes to {ociarchive_name}.stamp in
            # logdir if the compose succeeded. If the compose failed, an exception
            # will be raised.
            os.path.exists(
                os.path.join(self.logdir, "%s.stamp" % config["ociarchive_name"])
            )
            if config["version"] is None:
                filename = "%s.ociarchive" % config["ociarchive_name"]
            else:
                filename = (
                    "%s-%s.ociarchive" % (config["ociarchive_name"], config["version"]),
                )
            compose.notifier.send(
                "ostree_container",
                variant=variant.uid,
                arch=arch,
                filename=filename,
                version=config["version"],
                path=translate_path(compose, config["ociarchive_path"]),
                local_path=config["ociarchive_path"],
            )

        self.pool.log_info("[DONE ] %s" % (msg))

    def _run_ostree_container_cmd(
        self, compose, variant, arch, config, config_repo, extra_config_file=None
    ):
        args = OrderedDict(
            [
                ("log-dir", self.logdir),
                ("treefile", os.path.join(config_repo, config["treefile"])),
                ("version", util.version_generator(compose, config.get("version"))),
                ("extra-config", extra_config_file),
                ("ociarchive-path", config.get("ociarchive_path")),
                ("ociarchive-name", config.get("ociarchive_name")),
            ]
        )
        default_packages = ["pungi", "ostree", "rpm-ostree", "selinux-policy-targeted"]
        additional_packages = config.get("runroot_packages", [])
        packages = default_packages + additional_packages
        log_file = os.path.join(self.logdir, "runroot.log")
        # TODO: Use to get previous build
        mounts = [compose.topdir, config["ostree_repo"]]
        runroot = Runroot(compose, phase="ostree_container")

        if compose.conf["ostree_container_use_koji_plugin"]:
            runroot.run_pungi_ostree(
                dict(args),
                log_file=log_file,
                arch=arch,
                packages=packages,
                mounts=mounts,
                weight=compose.conf["runroot_weights"].get("ostree"),
            )
        else:
            cmd = ["pungi-make-ostree", "container"]
            for key, value in args.items():
                if value is True:
                    cmd.append("--%s" % key)
                elif value:
                    cmd.append("--%s=%s" % (key, value))

            runroot.run(
                cmd,
                log_file=log_file,
                arch=arch,
                packages=packages,
                mounts=mounts,
                new_chroot=True,
                weight=compose.conf["runroot_weights"].get("ostree"),
            )

    def _clone_repo(self, compose, repodir, url, branch):
        scm.get_dir_from_scm(
            {"scm": "git", "repo": url, "branch": branch, "dir": "."},
            repodir,
            compose=compose,
        )
