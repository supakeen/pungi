# -*- coding: utf-8 -*-

import os
from kobo.threads import ThreadPool, WorkerThread
from kobo import shortcuts
from productmd.images import Image

from . import base
from .. import util
from ..linker import Linker
from ..wrappers import kojiwrapper
from .image_build import EXTENSIONS


class KiwiBuildPhase(
    base.PhaseLoggerMixin, base.ImageConfigMixin, base.ConfigGuardedPhase
):
    name = "kiwibuild"

    def __init__(self, compose):
        super(KiwiBuildPhase, self).__init__(compose)
        self.pool = ThreadPool(logger=self.logger)

    def _get_arches(self, image_conf, arches):
        """Get an intersection of arches in the config dict and the given ones."""
        if "arches" in image_conf:
            arches = set(image_conf["arches"]) & arches
        return sorted(arches)

    @staticmethod
    def _get_repo_urls(compose, repos, arch="$basearch"):
        """
        Get list of repos with resolved repo URLs. Preserve repos defined
        as dicts.
        """
        resolved_repos = []

        for repo in repos:
            if isinstance(repo, dict):
                try:
                    url = repo["baseurl"]
                except KeyError:
                    raise RuntimeError(
                        "`baseurl` is required in repo dict %s" % str(repo)
                    )
                url = util.get_repo_url(compose, url, arch=arch)
                if url is None:
                    raise RuntimeError("Failed to resolve repo URL for %s" % str(repo))
                repo["baseurl"] = url
                resolved_repos.append(repo)
            else:
                repo = util.get_repo_url(compose, repo, arch=arch)
                if repo is None:
                    raise RuntimeError("Failed to resolve repo URL for %s" % repo)
                resolved_repos.append(repo)

        return resolved_repos

    def _get_repo(self, image_conf, variant):
        """
        Get a list of repos. First included are those explicitly listed in
        config, followed by by repo for current variant if it's not included in
        the list already.
        """
        repos = shortcuts.force_list(image_conf.get("repos", []))

        if not variant.is_empty and variant.uid not in repos:
            repos.append(variant.uid)

        return KiwiBuildPhase._get_repo_urls(self.compose, repos, arch="$arch")

    def run(self):
        for variant in self.compose.get_variants():
            arches = set([x for x in variant.arches if x != "src"])

            for image_conf in self.get_config_block(variant):
                build_arches = self._get_arches(image_conf, arches)
                if not build_arches:
                    self.log_debug("skip: no arches")
                    continue

                # these properties can be set per-image *or* as e.g.
                # kiwibuild_description_scm or global_release in the config
                generics = {
                    "release": self.get_release(image_conf),
                    "target": self.get_config(image_conf, "target"),
                    "descscm": self.get_config(image_conf, "description_scm"),
                    "descpath": self.get_config(image_conf, "description_path"),
                }

                repo = self._get_repo(image_conf, variant)

                failable_arches = image_conf.pop("failable", [])
                if failable_arches == ["*"]:
                    failable_arches = image_conf["arches"]

                self.pool.add(RunKiwiBuildThread(self.pool))
                self.pool.queue_put(
                    (
                        self.compose,
                        variant,
                        image_conf,
                        build_arches,
                        generics,
                        repo,
                        failable_arches,
                    )
                )

        self.pool.start()


class RunKiwiBuildThread(WorkerThread):
    def process(self, item, num):
        (compose, variant, config, arches, generics, repo, failable_arches) = item
        self.failable_arches = failable_arches
        # the Koji task as a whole can only fail if *all* arches are failable
        can_task_fail = set(failable_arches).issuperset(set(arches))
        self.num = num
        with util.failable(
            compose,
            can_task_fail,
            variant,
            "*",
            "kiwibuild",
            logger=self.pool._logger,
        ):
            self.worker(compose, variant, config, arches, generics, repo)

    def worker(self, compose, variant, config, arches, generics, repo):
        msg = "kiwibuild task for variant %s" % variant.uid
        self.pool.log_info("[BEGIN] %s" % msg)
        koji = kojiwrapper.KojiWrapper(compose)
        koji.login()

        task_id = koji.koji_proxy.kiwiBuild(
            generics["target"],
            arches,
            generics["descscm"],
            generics["descpath"],
            profile=config["kiwi_profile"],
            release=generics["release"],
            repos=repo,
            # this ensures the task won't fail if only failable arches fail
            optional_arches=self.failable_arches,
        )

        koji.save_task_id(task_id)

        # Wait for it to finish and capture the output into log file.
        log_dir = os.path.join(compose.paths.log.topdir(), "kiwibuild")
        util.makedirs(log_dir)
        log_file = os.path.join(
            log_dir, "%s-%s-watch-task.log" % (variant.uid, self.num)
        )
        if koji.watch_task(task_id, log_file) != 0:
            raise RuntimeError(
                "kiwiBuild: task %s failed: see %s for details" % (task_id, log_file)
            )

        # Refresh koji session which may have timed out while the task was
        # running. Watching is done via a subprocess, so the session is
        # inactive.
        koji = kojiwrapper.KojiWrapper(compose)

        linker = Linker(logger=self.pool._logger)

        # Process all images in the build. There should be one for each
        # architecture, but we don't verify that.
        paths = koji.get_image_paths(task_id)

        for arch, paths in paths.items():
            for path in paths:
                type_, suffix = _find_suffix(path)
                if not suffix:
                    # Path doesn't match any know type.
                    continue

                # image_dir is absolute path to which the image should be copied.
                # We also need the same path as relative to compose directory for
                # including in the metadata.
                image_dir = compose.paths.compose.image_dir(variant) % {"arch": arch}
                rel_image_dir = compose.paths.compose.image_dir(
                    variant, relative=True
                ) % {"arch": arch}
                util.makedirs(image_dir)

                filename = os.path.basename(path)

                image_dest = os.path.join(image_dir, filename)

                src_file = compose.koji_downloader.get_file(path)

                linker.link(src_file, image_dest, link_type=compose.conf["link_type"])

                # Update image manifest
                img = Image(compose.im)

                # Get the manifest type from the config if supplied, otherwise we
                # determine the manifest type based on the koji output
                img.type = type_
                img.format = suffix
                img.path = os.path.join(rel_image_dir, filename)
                img.mtime = util.get_mtime(image_dest)
                img.size = util.get_file_size(image_dest)
                img.arch = arch
                img.disc_number = 1  # We don't expect multiple disks
                img.disc_count = 1
                img.bootable = False
                img.subvariant = config.get("subvariant", variant.uid)
                setattr(img, "can_fail", arch in self.failable_arches)
                setattr(img, "deliverable", "kiwibuild")
                compose.im.add(variant=variant.uid, arch=arch, image=img)

        self.pool.log_info("[DONE ] %s (task id: %s)" % (msg, task_id))


def _find_suffix(path):
    for type_, suffixes in EXTENSIONS.items():
        for suffix in suffixes:
            if path.endswith(suffix):
                return type_, suffix
    return None, None
