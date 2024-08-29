import os

try:
    from unittest import mock
except ImportError:
    import mock

from pungi.phases.kiwibuild import KiwiBuildPhase, RunKiwiBuildThread
from tests.helpers import DummyCompose, PungiTestCase


MINIMAL_CONF = {
    "description_scm": "https://example.com/kiwi.git",
    "description_path": "Fedora.kiwi",
    "kiwi_profile": "Cloud-Base-Generic",
}


def _merge(a, b):
    """This would be a | b on 3.9 and later, or {**a, **b} or 3.5 and later."""
    c = a.copy()
    c.update(b)
    return c


@mock.patch("pungi.phases.kiwibuild.ThreadPool")
class TestKiwiBuildPhase(PungiTestCase):
    def test_minimal(self, ThreadPool):
        cfg = _merge({"target": "f40"}, MINIMAL_CONF)
        compose = DummyCompose(self.topdir, {"kiwibuild": {"^Server$": [cfg]}})

        self.assertValidConfig(compose.conf)

        phase = KiwiBuildPhase(compose)

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
                        "descscm": MINIMAL_CONF["description_scm"],
                        "descpath": MINIMAL_CONF["description_path"],
                        "type": None,
                        "type_attr": None,
                        "bundle_name_format": None,
                        "version": compose.image_version,
                        "repo_releasever": None,
                    },
                    [self.topdir + "/compose/Server/$arch/os"],
                    [],  # failable arches
                )
            )
        ]

    def test_full(self, ThreadPool):
        cfg = _merge(
            {
                "target": "f40",
                "release": "1234",
                "arches": ["x86_64"],
                "repos": ["https://example.com/repo/", "Client"],
                "failable": ["*"],
                "subvariant": "Test",
                "type": "custom",
                "type_attr": ["foo", "bar"],
                "bundle_name_format": "fmt",
                "version": "Rawhide",
                "repo_releasever": "41",
                "manifest_type": "live-kiwi",
            },
            MINIMAL_CONF,
        )
        compose = DummyCompose(self.topdir, {"kiwibuild": {"^Server$": [cfg]}})

        self.assertValidConfig(compose.conf)

        phase = KiwiBuildPhase(compose)

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
                        "descscm": MINIMAL_CONF["description_scm"],
                        "descpath": MINIMAL_CONF["description_path"],
                        "type": "custom",
                        "type_attr": ["foo", "bar"],
                        "bundle_name_format": "fmt",
                        "version": "Rawhide",
                        "repo_releasever": "41",
                    },
                    [
                        "https://example.com/repo/",
                        self.topdir + "/compose/Client/$arch/os",
                        self.topdir + "/compose/Server/$arch/os",
                    ],
                    ["x86_64"],
                )
            )
        ]

    def test_failable(self, ThreadPool):
        cfg = _merge({"target": "f40", "failable": ["x86_64"]}, MINIMAL_CONF)
        compose = DummyCompose(self.topdir, {"kiwibuild": {"^Server$": [cfg]}})

        self.assertValidConfig(compose.conf)

        phase = KiwiBuildPhase(compose)

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
                        "descscm": MINIMAL_CONF["description_scm"],
                        "descpath": MINIMAL_CONF["description_path"],
                        "type": None,
                        "type_attr": None,
                        "bundle_name_format": None,
                        "version": compose.image_version,
                        "repo_releasever": None,
                    },
                    [self.topdir + "/compose/Server/$arch/os"],
                    ["x86_64"],  # failable arches
                )
            )
        ]

    def test_with_phase_opts(self, ThreadPool):
        cfg = {"kiwi_profile": "Generic"}
        compose = DummyCompose(
            self.topdir,
            {
                "kiwibuild": {"^Server$": [cfg]},
                "kiwibuild_target": "f40",
                "kiwibuild_release": "1234",
                "kiwibuild_description_scm": "foo",
                "kiwibuild_description_path": "bar",
                "kiwibuild_type": "custom",
                "kiwibuild_type_attr": ["foo", "bar"],
                "kiwibuild_bundle_name_format": "fmt",
                "kiwibuild_version": "Rawhide",
                "kiwibuild_repo_releasever": "41",
            },
        )

        self.assertValidConfig(compose.conf)

        phase = KiwiBuildPhase(compose)

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
                        "descscm": "foo",
                        "descpath": "bar",
                        "type": "custom",
                        "type_attr": ["foo", "bar"],
                        "bundle_name_format": "fmt",
                        "version": "Rawhide",
                        "repo_releasever": "41",
                    },
                    [self.topdir + "/compose/Server/$arch/os"],
                    [],  # failable arches
                )
            )
        ]

    def test_with_global_opts(self, ThreadPool):
        cfg = MINIMAL_CONF
        compose = DummyCompose(
            self.topdir,
            {
                "kiwibuild": {"^Server$": [cfg]},
                "global_target": "f40",
                "global_release": "1234",
                "global_version": "41",
            },
        )

        self.assertValidConfig(compose.conf)

        phase = KiwiBuildPhase(compose)

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
                        "descscm": MINIMAL_CONF["description_scm"],
                        "descpath": MINIMAL_CONF["description_path"],
                        "type": None,
                        "type_attr": None,
                        "bundle_name_format": None,
                        "version": "41",
                        "repo_releasever": None,
                    },
                    [self.topdir + "/compose/Server/$arch/os"],
                    [],  # failable arches
                )
            )
        ]


@mock.patch("pungi.phases.kiwibuild.Linker")
@mock.patch("pungi.util.get_mtime")
@mock.patch("pungi.util.get_file_size")
@mock.patch("pungi.wrappers.kojiwrapper.KojiWrapper")
class TestKiwiBuildThread(PungiTestCase):
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
                "kiwibuild_bundle_format": "%N-%P-40_Beta-%I.%A.%T",
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

        KojiWrapper.return_value.koji_proxy.kiwiBuild.return_value = 1234
        KojiWrapper.return_value.watch_task.return_value = 0

        t = RunKiwiBuildThread(pool)
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
                    "descscm": MINIMAL_CONF["description_scm"],
                    "descpath": MINIMAL_CONF["description_path"],
                    "type": "t",
                    "type_attr": ["ta"],
                    "bundle_name_format": "fmt",
                    "version": "v",
                    "repo_releasever": "r",
                },
                [self.repo],
                [],
            ),
            1,
        )

        assert KojiWrapper.return_value.koji_proxy.kiwiBuild.mock_calls == [
            mock.call(
                "f40",
                ["amd64", "x86_64"],
                MINIMAL_CONF["description_scm"],
                MINIMAL_CONF["description_path"],
                profile=MINIMAL_CONF["kiwi_profile"],
                release="1.6",
                repos=[self.repo],
                type="t",
                type_attr=["ta"],
                result_bundle_name_format="fmt",
                optional_arches=[],
                version="v",
                repo_releasever="r",
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
                "kiwibuild_bundle_format": "%N-%P-40_Beta-%I.%A.%T",
            },
        )
        config = _merge(
            {"subvariant": "Test", "manifest_type": "live-kiwi"}, MINIMAL_CONF
        )
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

        KojiWrapper.return_value.koji_proxy.kiwiBuild.return_value = 1234
        KojiWrapper.return_value.watch_task.return_value = 0

        t = RunKiwiBuildThread(pool)
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
                    "descscm": MINIMAL_CONF["description_scm"],
                    "descpath": MINIMAL_CONF["description_path"],
                    "type": "t",
                    "type_attr": ["ta"],
                    "bundle_name_format": "fmt",
                    "version": "v",
                    "repo_releasever": "r",
                },
                [self.repo],
                [],
            ),
            1,
        )

        assert KojiWrapper.return_value.koji_proxy.kiwiBuild.mock_calls == [
            mock.call(
                "f40",
                ["amd64", "x86_64"],
                MINIMAL_CONF["description_scm"],
                MINIMAL_CONF["description_path"],
                profile=MINIMAL_CONF["kiwi_profile"],
                release="1.6",
                repos=[self.repo],
                type="t",
                type_attr=["ta"],
                result_bundle_name_format="fmt",
                optional_arches=[],
                version="v",
                repo_releasever="r",
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
            assert "live-kiwi" == image.type
            assert image.bootable
            assert "Test" == image.subvariant

    def test_handle_koji_fail(self, KojiWrapper, get_file_size, get_mtime, Linker):
        self.repo = self.topdir + "/compose/Server/$arch/os"
        compose = DummyCompose(self.topdir, {"koji_profile": "koji"})
        config = MINIMAL_CONF
        pool = mock.Mock()

        get_image_paths = KojiWrapper.return_value.get_image_paths

        KojiWrapper.return_value.koji_proxy.kiwiBuild.return_value = 1234
        KojiWrapper.return_value.watch_task.return_value = 1

        t = RunKiwiBuildThread(pool)
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
                        "descscm": MINIMAL_CONF["description_scm"],
                        "descpath": MINIMAL_CONF["description_path"],
                        "type": None,
                        "type_attr": None,
                        "bundle_name_format": None,
                        "version": None,
                        "repo_releasever": None,
                    },
                    [self.repo],
                    [],
                ),
                1,
            )
            assert False, "Exception should have been raised"
        except RuntimeError:
            pass

        assert len(KojiWrapper.return_value.koji_proxy.kiwiBuild.mock_calls) == 1
        assert get_image_paths.mock_calls == []
        assert Linker.return_value.link.mock_calls == []
        assert len(compose.im.add.call_args_list) == 0

    def test_handle_fail_on_optional_arch(
        self, KojiWrapper, get_file_size, get_mtime, Linker
    ):
        self.repo = self.topdir + "/compose/Server/$arch/os"
        compose = DummyCompose(self.topdir, {"koji_profile": "koji"})
        config = MINIMAL_CONF
        pool = mock.Mock()

        get_image_paths = KojiWrapper.return_value.get_image_paths
        get_image_paths.return_value = {
            "x86_64": [
                "/koji/task/1234/FCBG.x86_64-Rawhide-1.6.packages",
                "/koji/task/1234/FCBG.x86_64-Rawhide-1.6.qcow2",
            ],
        }

        KojiWrapper.return_value.koji_proxy.kiwiBuild.return_value = 1234
        KojiWrapper.return_value.watch_task.return_value = 0

        t = RunKiwiBuildThread(pool)
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
                    "descscm": MINIMAL_CONF["description_scm"],
                    "descpath": MINIMAL_CONF["description_path"],
                    "type": None,
                    "type_attr": None,
                    "bundle_name_format": None,
                    "version": None,
                    "repo_releasever": None,
                },
                [self.repo],
                ["amd64"],
            ),
            1,
        )

        assert KojiWrapper.return_value.koji_proxy.kiwiBuild.mock_calls == [
            mock.call(
                "f40",
                ["amd64", "x86_64"],
                MINIMAL_CONF["description_scm"],
                MINIMAL_CONF["description_path"],
                profile=MINIMAL_CONF["kiwi_profile"],
                release="1.6",
                repos=[self.repo],
                type=None,
                type_attr=None,
                result_bundle_name_format=None,
                optional_arches=["amd64"],
                version=None,
                repo_releasever=None,
            )
        ]
        assert get_image_paths.mock_calls == [mock.call(1234)]
        assert os.path.isdir(self._img_path("x86_64"))
        assert not os.path.isdir(self._img_path("amd64"))
        assert Linker.return_value.link.mock_calls == [
            mock.call(
                "/koji/task/1234/FCBG.x86_64-Rawhide-1.6.qcow2",
                self._img_path("x86_64", "FCBG.x86_64-Rawhide-1.6.qcow2"),
                link_type="hardlink-or-copy",
            ),
        ]

        assert len(compose.im.add.call_args_list) == 1
        _, kwargs = compose.im.add.call_args_list[0]
        image = kwargs["image"]
        expected_path = "Server/x86_64/images/FCBG.x86_64-Rawhide-1.6.qcow2"
        assert kwargs["variant"] == "Server"
        assert kwargs["arch"] == "x86_64"
        assert kwargs["arch"] == image.arch
        assert image.path == expected_path
        assert "qcow2" == image.format
        assert "qcow2" == image.type
        assert "Server" == image.subvariant
