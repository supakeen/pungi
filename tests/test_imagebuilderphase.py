import os
from unittest import mock

from pungi.phases.imagebuilder import ImageBuilderPhase, RunImageBuilderThread
from tests.helpers import DummyCompose, PungiTestCase


MINIMAL_CONF = {
    "types": ["minimal-raw-xz"],
    "name": "Test",
}


def _merge(a, b):
    """This would be a | b on 3.9 and later, or {**a, **b} or 3.5 and later."""
    c = a.copy()
    c.update(b)
    return c


@mock.patch("pungi.phases.imagebuilder.ThreadPool")
class TestImageBuilderPhase(PungiTestCase):
    def test_minimal(self, ThreadPool):
        cfg = _merge({"target": "f40"}, MINIMAL_CONF)
        compose = DummyCompose(self.topdir, {"imagebuilder": {"^Server$": [cfg]}})

        self.assertValidConfig(compose.conf)

        phase = ImageBuilderPhase(compose)

        phase.run()
        phase.pool.add.assert_called()
        assert phase.pool.queue_put.call_args_list == [
            mock.call(
                (
                    compose,
                    compose.variants["Server"],
                    cfg,
                    ["amd64", "x86_64"],
                    {
                        "release": None,
                        "target": "f40",
                        "types": ["minimal-raw-xz"],
                        "seed": None,
                        "scratch": None,
                        "version": compose.image_version,
                    },
                    [self.topdir + "/compose/Server/$arch/os"],
                    [],
                )
            )
        ]

    def test_full(self, ThreadPool):
        cfg = _merge(
            MINIMAL_CONF,
            {
                "target": "f40",
                "release": "1234",
                "arches": ["x86_64"],
                "repos": ["https://example.com/repo/", "Client"],
                "types": ["custom"],
                "version": "Rawhide",
                "manifest_type": "custom-type",
            },
        )
        compose = DummyCompose(self.topdir, {"imagebuilder": {"^Server$": [cfg]}})

        self.assertValidConfig(compose.conf)

        phase = ImageBuilderPhase(compose)

        phase.run()
        phase.pool.add.assert_called()

        assert phase.pool.queue_put.call_args_list == [
            mock.call(
                (
                    compose,
                    compose.variants["Server"],
                    cfg,
                    ["x86_64"],
                    {
                        "release": "1234",
                        "target": "f40",
                        "types": ["custom"],
                        "seed": None,
                        "scratch": None,
                        "version": "Rawhide",
                    },
                    [
                        "https://example.com/repo/",
                        self.topdir + "/compose/Client/$arch/os",
                        self.topdir + "/compose/Server/$arch/os",
                    ],
                    [],
                )
            )
        ]

    def test_failable(self, ThreadPool):
        cfg = _merge({"target": "f40", "failable": ["x86_64"]}, MINIMAL_CONF)
        compose = DummyCompose(self.topdir, {"imagebuilder": {"^Server$": [cfg]}})

        self.assertValidConfig(compose.conf)

        phase = ImageBuilderPhase(compose)

        phase.run()
        phase.pool.add.assert_called()
        assert phase.pool.queue_put.call_args_list == [
            mock.call(
                (
                    compose,
                    compose.variants["Server"],
                    cfg,
                    ["amd64", "x86_64"],
                    {
                        "release": None,
                        "target": "f40",
                        "types": ["minimal-raw-xz"],
                        "seed": None,
                        "scratch": None,
                        "version": compose.image_version,
                    },
                    [self.topdir + "/compose/Server/$arch/os"],
                    ["x86_64"],
                )
            )
        ]

    def test_with_phase_opts(self, ThreadPool):
        cfg = {"name": "Test", "types": ["minimal-raw-xz"]}
        compose = DummyCompose(
            self.topdir,
            {
                "imagebuilder": {"^Server$": [cfg]},
                "imagebuilder_target": "f40",
                "imagebuilder_release": "1234",
                "imagebuilder_version": "Rawhide",
            },
        )

        self.assertValidConfig(compose.conf)

        phase = ImageBuilderPhase(compose)

        phase.run()
        phase.pool.add.assert_called()
        assert phase.pool.queue_put.call_args_list == [
            mock.call(
                (
                    compose,
                    compose.variants["Server"],
                    cfg,
                    ["amd64", "x86_64"],
                    {
                        "release": "1234",
                        "target": "f40",
                        "types": ["minimal-raw-xz"],
                        "seed": None,
                        "scratch": None,
                        "version": "Rawhide",
                    },
                    [self.topdir + "/compose/Server/$arch/os"],
                    [],
                )
            )
        ]

    def test_with_global_opts(self, ThreadPool):
        cfg = MINIMAL_CONF
        compose = DummyCompose(
            self.topdir,
            {
                "imagebuilder": {"^Server$": [cfg]},
                "global_target": "f40",
                "global_release": "1234",
                "global_version": "41",
            },
        )

        self.assertValidConfig(compose.conf)

        phase = ImageBuilderPhase(compose)

        phase.run()
        phase.pool.add.assert_called()
        assert phase.pool.queue_put.call_args_list == [
            mock.call(
                (
                    compose,
                    compose.variants["Server"],
                    cfg,
                    ["amd64", "x86_64"],
                    {
                        "release": "1234",
                        "target": "f40",
                        "types": ["minimal-raw-xz"],
                        "seed": None,
                        "scratch": None,
                        "version": "41",
                    },
                    [self.topdir + "/compose/Server/$arch/os"],
                    [],
                )
            )
        ]


@mock.patch("pungi.phases.imagebuilder.Linker")
@mock.patch("pungi.util.get_mtime")
@mock.patch("pungi.util.get_file_size")
@mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
class TestImageBuilderThread(PungiTestCase):
    def _img_path(self, arch, filename=None, dir=None):
        dir = dir or "images"
        path = self.topdir + "/compose/Server/%s/%s" % (arch, dir)
        if filename:
            path += "/" + filename
        return path

    def test_process_vagrant_box(self, KojiWrapper, get_file_size, get_mtime, Linker):
        img_name = "FCBG.{arch}-Rawhide-1.6.vagrant.libvirt.box"
        self.repo = self.topdir + "/compose/Server/$arch/os"
        compose = DummyCompose(
            self.topdir,
            {
                "koji_profile": "koji",
            },
        )
        config = _merge({"subvariant": "Test"}, MINIMAL_CONF)
        pool = mock.Mock()

        get_image_paths = KojiWrapper.return_value.get_image_paths
        get_image_paths.return_value = {
            "x86_64": [
                "/koji/task/1234/FCBG.x86_64-Rawhide-1.6.packages",
                "/koji/task/1234/%s" % img_name.format(arch="x86_64"),
            ],
            "amd64": [
                "/koji/task/1234/FCBG.amd64-Rawhide-1.6.packages",
                "/koji/task/1234/%s" % img_name.format(arch="amd64"),
            ],
        }

        KojiWrapper.return_value.koji_proxy.imageBuilderBuild.return_value = 1234
        KojiWrapper.return_value.watch_task.return_value = 0

        t = RunImageBuilderThread(pool)
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579
        t.process(
            (
                compose,
                compose.variants["Server"],
                config,
                ["amd64", "x86_64"],
                {
                    "release": "1.6",
                    "target": "f40",
                    "types": ["t"],
                    "version": "v",
                },
                [self.repo],
                [],
            ),
            1,
        )

        assert KojiWrapper.return_value.koji_proxy.imageBuilderBuild.mock_calls == [
            mock.call(
                "f40",
                ["amd64", "x86_64"],
                types=["t"],
                name="Test",
                version="v",
                opts={
                    "repos": [self.repo],
                    "release": "1.6",
                },
            )
        ]

        assert get_image_paths.mock_calls == [mock.call(1234)]
        assert os.path.isdir(self._img_path("x86_64"))
        assert os.path.isdir(self._img_path("amd64"))
        Linker.return_value.link.assert_has_calls(
            [
                mock.call(
                    "/koji/task/1234/FCBG.amd64-Rawhide-1.6.vagrant.libvirt.box",
                    self._img_path("amd64", img_name.format(arch="amd64")),
                    link_type="hardlink-or-copy",
                ),
                mock.call(
                    "/koji/task/1234/FCBG.x86_64-Rawhide-1.6.vagrant.libvirt.box",
                    self._img_path("x86_64", img_name.format(arch="x86_64")),
                    link_type="hardlink-or-copy",
                ),
            ],
            any_order=True,
        )

        assert len(compose.im.add.call_args_list) == 2
        for call in compose.im.add.call_args_list:
            _, kwargs = call
            image = kwargs["image"]
            expected_path = "Server/{0.arch}/images/{1}".format(
                image, img_name.format(arch=image.arch)
            )
            assert kwargs["variant"] == "Server"
            assert kwargs["arch"] in ("amd64", "x86_64")
            assert kwargs["arch"] == image.arch
            assert image.path == expected_path
            assert "vagrant-libvirt.box" == image.format
            assert "vagrant-libvirt" == image.type
            assert "Test" == image.subvariant
            assert not image.bootable

    def test_process_iso(self, KojiWrapper, get_file_size, get_mtime, Linker):
        img_name = "FCBG.{arch}-Rawhide-1.6.iso"
        self.repo = self.topdir + "/compose/Server/$arch/os"
        compose = DummyCompose(
            self.topdir,
            {
                "koji_profile": "koji",
            },
        )
        config = _merge({"subvariant": "Test", "name": "Test"}, MINIMAL_CONF)
        pool = mock.Mock()

        get_image_paths = KojiWrapper.return_value.get_image_paths
        get_image_paths.return_value = {
            "x86_64": [
                "/koji/task/1234/FCBG.x86_64-Rawhide-1.6.packages",
                "/koji/task/1234/%s" % img_name.format(arch="x86_64"),
            ],
            "amd64": [
                "/koji/task/1234/FCBG.amd64-Rawhide-1.6.packages",
                "/koji/task/1234/%s" % img_name.format(arch="amd64"),
            ],
        }

        KojiWrapper.return_value.koji_proxy.imageBuilderBuild.return_value = 1234
        KojiWrapper.return_value.watch_task.return_value = 0

        t = RunImageBuilderThread(pool)
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579
        t.process(
            (
                compose,
                compose.variants["Server"],
                config,
                ["amd64", "x86_64"],
                {
                    "release": "1.6",
                    "target": "f40",
                    "types": ["t"],
                    "version": "v",
                },
                [self.repo],
                [],
            ),
            1,
        )

        assert KojiWrapper.return_value.koji_proxy.imageBuilderBuild.mock_calls == [
            mock.call(
                "f40",
                ["amd64", "x86_64"],
                types=["t"],
                name="Test",
                version="v",
                opts={
                    "repos": [self.repo],
                    "release": "1.6",
                },
            )
        ]

        assert get_image_paths.mock_calls == [mock.call(1234)]
        assert os.path.isdir(self._img_path("x86_64", dir="iso"))
        assert os.path.isdir(self._img_path("amd64", dir="iso"))
        Linker.return_value.link.assert_has_calls(
            [
                mock.call(
                    "/koji/task/1234/FCBG.amd64-Rawhide-1.6.iso",
                    self._img_path("amd64", img_name.format(arch="amd64"), dir="iso"),
                    link_type="hardlink-or-copy",
                ),
                mock.call(
                    "/koji/task/1234/FCBG.x86_64-Rawhide-1.6.iso",
                    self._img_path("x86_64", img_name.format(arch="x86_64"), dir="iso"),
                    link_type="hardlink-or-copy",
                ),
            ],
            any_order=True,
        )

        assert len(compose.im.add.call_args_list) == 2
        for call in compose.im.add.call_args_list:
            _, kwargs = call
            image = kwargs["image"]
            expected_path = "Server/{0.arch}/iso/{1}".format(
                image, img_name.format(arch=image.arch)
            )
            assert kwargs["variant"] == "Server"
            assert kwargs["arch"] in ("amd64", "x86_64")
            assert kwargs["arch"] == image.arch
            assert image.path == expected_path
            assert "iso" == image.format
            assert "boot" == image.type
            assert image.bootable
            assert "Test" == image.subvariant

    def test_handle_koji_fail(self, KojiWrapper, get_file_size, get_mtime, Linker):
        self.repo = self.topdir + "/compose/Server/$arch/os"
        compose = DummyCompose(self.topdir, {"koji_profile": "koji"})
        config = MINIMAL_CONF
        pool = mock.Mock()

        get_image_paths = KojiWrapper.return_value.get_image_paths

        KojiWrapper.return_value.koji_proxy.imageBuilderBuild.return_value = 1234
        KojiWrapper.return_value.watch_task.return_value = 1

        t = RunImageBuilderThread(pool)
        try:
            t.process(
                (
                    compose,
                    compose.variants["Server"],
                    config,
                    ["amd64", "x86_64"],
                    {
                        "release": "1.6",
                        "target": "f40",
                        "types": ["minimal-raw-xz"],
                        "version": None,
                    },
                    [self.repo],
                    [],
                ),
                1,
            )
            assert False, "Exception should have been raised"
        except RuntimeError:
            pass

        assert (
            len(KojiWrapper.return_value.koji_proxy.imageBuilderBuild.mock_calls) == 1
        )
        assert get_image_paths.mock_calls == []
        assert Linker.return_value.link.mock_calls == []
        assert len(compose.im.add.call_args_list) == 0
