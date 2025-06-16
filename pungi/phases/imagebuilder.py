# -*- coding: utf-8 -*-

import os
from kobo.threads import ThreadPool
from kobo import shortcuts
from productmd.images import Image

from . import base
from .. import util
from ..linker import Linker
from ..wrappers import kojiwrapper
from .image_build import EXTENSIONS
from ..threading import TelemetryWorkerThread as WorkerThread


IMAGEBUILDEREXTENSIONS = [
    ("vagrant-libvirt", ["vagrant.libvirt.box"], "vagrant-libvirt.box"),
    (
        "vagrant-virtualbox",
        ["vagrant.virtualbox.box"],
        "vagrant-virtualbox.box",
    ),
    ("container", ["oci.tar.xz"], "tar.xz"),
    ("wsl2", ["wsl"], "wsl"),
    # .iso images can be of many types - boot, cd, dvd, live... -
    # so 'boot' is just a default guess. 'iso' is not a valid
    # productmd image type
    ("boot", [".iso"], "iso"),
]


class ImageBuilderPhase(
    base.PhaseLoggerMixin, base.ImageConfigMixin, base.ConfigGuardedPhase
):
    name = "imagebuilder"

    def __init__(self, compose):
        super(ImageBuilderPhase, self).__init__(compose)
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

        return ImageBuilderPhase._get_repo_urls(self.compose, repos, arch="$arch")

    def run(self):
        for variant in self.compose.get_variants():
            arches = set([x for x in variant.arches if x != "src"])

            for image_conf in self.get_config_block(variant):
                build_arches = self._get_arches(image_conf, arches)
                if not build_arches:
                    self.log_debug("skip: no arches")
                    continue

                # these properties can be set per-image *or* as e.g.
                # imagebuilder_release or global_release in the config
                generics = {
                    "release": self.get_release(image_conf),
                    "target": self.get_config(image_conf, "target"),
                    "types": self.get_config(image_conf, "types"),
                    "seed": self.get_config(image_conf, "seed"),
                    "scratch": self.get_config(image_conf, "scratch"),
                    "version": self.get_version(image_conf),
                }

                repo = self._get_repo(image_conf, variant)

                failable_arches = image_conf.pop("failable", [])
                if failable_arches == ["*"]:
                    failable_arches = image_conf["arches"]

                self.pool.add(RunImageBuilderThread(self.pool))
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


class RunImageBuilderThread(WorkerThread):
    def process(self, item, num):
        (compose, variant, config, arches, generics, repo, failable_arches) = item
        self.failable_arches = []
        # the Koji task as a whole can only fail if *all* arches are failable
        can_task_fail = set(self.failable_arches).issuperset(set(arches))
        self.num = num
        with util.failable(
            compose,
            can_task_fail,
            variant,
            "*",
            "imageBuilderBuild",
            logger=self.pool._logger,
        ):
            self.worker(compose, variant, config, arches, generics, repo)

    def worker(self, compose, variant, config, arches, generics, repo):
        msg = "imageBuilderBuild task for variant %s" % variant.uid
        self.pool.log_info("[BEGIN] %s" % msg)
        koji = kojiwrapper.KojiWrapper(compose)
        koji.login()

        opts = {}
        opts["repos"] = repo

        if generics.get("release"):
            opts["release"] = generics["release"]

        if generics.get("seed"):
            opts["seed"] = generics["seed"]

        if generics.get("scratch"):
            opts["scratch"] = generics["scratch"]

        if config.get("ostree"):
            opts["ostree"] = config["ostree"]

        if config.get("blueprint"):
            opts["blueprint"] = config["blueprint"]

        task_id = koji.koji_proxy.imageBuilderBuild(
            generics["target"],
            arches,
            types=generics["types"],
            name=config["name"],
            version=generics["version"],
            opts=opts,
        )

        koji.save_task_id(task_id)

        # Wait for it to finish and capture the output into log file.
        log_dir = os.path.join(compose.paths.log.topdir(), "imageBuilderBuild")
        util.makedirs(log_dir)
        log_file = os.path.join(
            log_dir, "%s-%s-watch-task.log" % (variant.uid, self.num)
        )
        if koji.watch_task(task_id, log_file) != 0:
            raise RuntimeError(
                "imageBuilderBuild task failed: %s. See %s for details"
                % (task_id, log_file)
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
                type_, format_ = _find_type_and_format(path)
                if not format_:
                    # Path doesn't match any known type.
                    continue

                # image_dir is absolute path to which the image should be copied.
                # We also need the same path as relative to compose directory for
                # including in the metadata.
                if format_ == "iso":
                    # If the produced image is actually an ISO, it should go to
                    # iso/ subdirectory.
                    image_dir = compose.paths.compose.iso_dir(arch, variant)
                    rel_image_dir = compose.paths.compose.iso_dir(
                        arch, variant, relative=True
                    )
                else:
                    image_dir = compose.paths.compose.image_dir(variant) % {
                        "arch": arch
                    }
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

                # If user configured exact type, use it, otherwise try to
                # figure it out based on the koji output.
                img.type = config.get("manifest_type", type_)
                img.format = format_
                img.path = os.path.join(rel_image_dir, filename)
                img.mtime = util.get_mtime(image_dest)
                img.size = util.get_file_size(image_dest)
                img.arch = arch
                img.disc_number = 1  # We don't expect multiple disks
                img.disc_count = 1

                img.bootable = format_ == "iso"
                img.subvariant = config.get("subvariant", variant.uid)
                setattr(img, "can_fail", arch in self.failable_arches)
                setattr(img, "deliverable", "imageBuilderBuild")
                compose.im.add(variant=variant.uid, arch=arch, image=img)

        self.pool.log_info("[DONE ] %s (task id: %s)" % (msg, task_id))


def _find_type_and_format(path):
    # these are our image-builder-exclusive mappings for images whose extensions
    # aren't quite the same as imagefactory. they come first as we
    # want our oci.tar.xz mapping to win over the tar.xz one in
    # EXTENSIONS
    for type_, suffixes, format_ in IMAGEBUILDEREXTENSIONS:
        if any(path.endswith(suffix) for suffix in suffixes):
            return type_, format_
    for type_, suffixes in EXTENSIONS.items():
        for suffix in suffixes:
            if path.endswith(suffix):
                return type_, suffix
    return None, None
