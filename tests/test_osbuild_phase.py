# -*- coding: utf-8 -*-

import mock

import os
import shutil
import tempfile
import unittest

import koji as orig_koji

from tests import helpers
from pungi import compose
from pungi.phases import osbuild
from pungi.checks import validate


class OSBuildPhaseHelperFuncsTest(unittest.TestCase):
    @mock.patch("pungi.compose.ComposeInfo")
    def setUp(self, ci):
        self.tmp_dir = tempfile.mkdtemp()
        conf = {"translate_paths": [(self.tmp_dir, "http://example.com")]}
        ci.return_value.compose.respin = 0
        ci.return_value.compose.id = "RHEL-8.0-20180101.n.0"
        ci.return_value.compose.date = "20160101"
        ci.return_value.compose.type = "nightly"
        ci.return_value.compose.type_suffix = ".n"
        ci.return_value.compose.label = "RC-1.0"
        ci.return_value.compose.label_major_version = "1"

        compose_dir = os.path.join(self.tmp_dir, ci.return_value.compose.id)
        self.compose = compose.Compose(conf, compose_dir)
        server_variant = mock.Mock(uid="Server", type="variant")
        client_variant = mock.Mock(uid="Client", type="variant")
        self.compose.all_variants = {
            "Server": server_variant,
            "Client": client_variant,
        }

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test__get_repo_urls(self):
        repos = [
            "http://example.com/repo",
            "Server",
            {
                "baseurl": "Client",
                "package_sets": ["build"],
            },
            {
                "baseurl": "ftp://example.com/linux/repo",
                "package_sets": ["build"],
            },
        ]

        expect = [
            "http://example.com/repo",
            "http://example.com/RHEL-8.0-20180101.n.0/compose/Server/$basearch/os",
            {
                "baseurl": "http://example.com/RHEL-8.0-20180101.n.0/compose/Client/"
                + "$basearch/os",
                "package_sets": ["build"],
            },
            {
                "baseurl": "ftp://example.com/linux/repo",
                "package_sets": ["build"],
            },
        ]

        self.assertEqual(
            osbuild.OSBuildPhase._get_repo_urls(self.compose, repos), expect
        )


class OSBuildPhaseTest(helpers.PungiTestCase):
    @mock.patch("pungi.phases.osbuild.ThreadPool")
    def test_run(self, ThreadPool):
        cfg = {
            "name": "test-image",
            "distro": "rhel-8",
            "version": "1",
            "target": "image-target",
            "arches": ["x86_64"],
            "failable": ["x86_64"],
            "image_types": ["qcow2"],
        }
        compose = helpers.DummyCompose(
            self.topdir, {"osbuild": {"^Everything$": [cfg]}}
        )

        self.assertValidConfig(compose.conf)

        pool = ThreadPool.return_value

        phase = osbuild.OSBuildPhase(compose)
        phase.run()

        self.assertEqual(len(pool.add.call_args_list), 1)
        self.assertEqual(
            pool.queue_put.call_args_list,
            [
                mock.call(
                    (
                        compose,
                        compose.variants["Everything"],
                        cfg,
                        ["x86_64"],
                        "1",
                        None,
                        "image-target",
                        [self.topdir + "/compose/Everything/$arch/os"],
                        ["x86_64"],
                    ),
                ),
            ],
        )

    @mock.patch("pungi.phases.osbuild.ThreadPool")
    def test_run_with_global_options(self, ThreadPool):
        cfg = {
            "name": "test-image",
            "distro": "rhel-8",
            "image_types": ["qcow2"],
        }
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "osbuild": {"^Everything$": [cfg]},
                "osbuild_target": "image-target",
                "osbuild_version": "1",
                "osbuild_release": "2",
            },
        )

        self.assertValidConfig(compose.conf)

        pool = ThreadPool.return_value

        phase = osbuild.OSBuildPhase(compose)
        phase.run()

        self.assertEqual(len(pool.add.call_args_list), 1)
        self.assertEqual(
            pool.queue_put.call_args_list,
            [
                mock.call(
                    (
                        compose,
                        compose.variants["Everything"],
                        cfg,
                        sorted(compose.variants["Everything"].arches),
                        "1",
                        "2",
                        "image-target",
                        [self.topdir + "/compose/Everything/$arch/os"],
                        [],
                    ),
                ),
            ],
        )

    @mock.patch("pungi.phases.osbuild.ThreadPool")
    def test_skip_without_config(self, ThreadPool):
        compose = helpers.DummyCompose(self.topdir, {})
        compose.just_phases = None
        compose.skip_phases = []
        phase = osbuild.OSBuildPhase(compose)
        self.assertTrue(phase.skip())

    def test_fail_multiple_image_types(self):
        cfg = {
            "name": "test-image",
            "distro": "rhel-8",
            # more than one image type is not allowed
            "image_types": ["qcow2", "rhel-ec2"],
        }
        compose = helpers.DummyCompose(
            self.topdir,
            {
                "osbuild": {"^Everything$": [cfg]},
                "osbuild_target": "image-target",
                "osbuild_version": "1",
                "osbuild_release": "2",
            },
        )
        self.assertNotEqual(validate(compose.conf), ([], []))

    @mock.patch("pungi.phases.osbuild.ThreadPool")
    def test_rich_repos(self, ThreadPool):
        repo = {"baseurl": "http://example.com/repo", "package_sets": ["build"]}
        cfg = {
            "name": "test-image",
            "distro": "rhel-8",
            "version": "1",
            "target": "image-target",
            "arches": ["x86_64"],
            "image_types": ["qcow2"],
            "repo": [repo],
        }
        compose = helpers.DummyCompose(
            self.topdir, {"osbuild": {"^Everything$": [cfg]}}
        )

        self.assertValidConfig(compose.conf)

        pool = ThreadPool.return_value

        phase = osbuild.OSBuildPhase(compose)
        phase.run()

        self.assertEqual(len(pool.add.call_args_list), 1)
        self.assertEqual(
            pool.queue_put.call_args_list,
            [
                mock.call(
                    (
                        compose,
                        compose.variants["Everything"],
                        cfg,
                        ["x86_64"],
                        "1",
                        None,
                        "image-target",
                        [repo, self.topdir + "/compose/Everything/$arch/os"],
                        [],
                    ),
                ),
            ],
        )


class RunOSBuildThreadTest(helpers.PungiTestCase):
    def setUp(self):
        super(RunOSBuildThreadTest, self).setUp()
        self.pool = mock.Mock()
        self.t = osbuild.RunOSBuildThread(self.pool)
        self.compose = helpers.DummyCompose(
            self.topdir,
            {
                "koji_profile": "koji",
                "translate_paths": [(self.topdir, "http://root")],
            },
        )

    def make_fake_watch(self, retval):
        def inner(task_id, log_file):
            with open(log_file, "w") as f:
                f.write("Creating compose: test-image-1-1 1234\n")
            return retval

        return inner

    @mock.patch("pungi.util.get_file_size", new=lambda fp: 65536)
    @mock.patch("pungi.util.get_mtime", new=lambda fp: 1024)
    @mock.patch("pungi.phases.osbuild.Linker")
    @mock.patch("pungi.phases.osbuild.kojiwrapper.KojiWrapper")
    def test_process(self, KojiWrapper, Linker):
        cfg = {"name": "test-image", "distro": "rhel-8", "image_types": ["qcow2"]}
        build_id = 5678
        koji = KojiWrapper.return_value
        koji.watch_task.side_effect = self.make_fake_watch(0)
        koji.koji_proxy.osbuildImage.return_value = 1234
        koji.koji_proxy.getTaskResult.return_value = {
            "composer": {"server": "https://composer.osbuild.org", "id": ""},
            "koji": {"build": build_id},
        }
        koji.koji_proxy.getBuild.return_value = {
            "build_id": build_id,
            "name": "test-image",
            "version": "1",
            "release": "1",
        }
        koji.koji_proxy.listArchives.return_value = [
            {
                "extra": {"image": {"arch": "aarch64"}},
                "filename": "disk.aarch64.qcow2",
                "type_name": "qcow2",
            },
            {
                "extra": {"image": {"arch": "x86_64"}},
                "filename": "disk.x86_64.qcow2",
                "type_name": "qcow2",
            },
        ]
        koji.koji_module.pathinfo = orig_koji.pathinfo

        self.t.process(
            (
                self.compose,
                self.compose.variants["Everything"],
                cfg,
                ["aarch64", "x86_64"],
                "1",  # version
                "15",  # release
                "image-target",
                [
                    self.topdir + "/compose/Everything/$arch/os",
                    {
                        "baseurl": self.topdir + "/compose/Everything/$arch/os",
                        "package_sets": ["build"],
                    },
                ],
                ["x86_64"],
            ),
            1,
        )

        # Verify two Koji instances were created.
        self.assertEqual(len(KojiWrapper.call_args), 2)
        # Verify correct calls to Koji
        self.assertEqual(
            koji.mock_calls,
            [
                mock.call.login(),
                mock.call.koji_proxy.osbuildImage(
                    "test-image",
                    "1",
                    "rhel-8",
                    ["qcow2"],
                    "image-target",
                    ["aarch64", "x86_64"],
                    opts={
                        "release": "15",
                        "repo": [
                            self.topdir + "/compose/Everything/$arch/os",
                            {
                                "baseurl": self.topdir + "/compose/Everything/$arch/os",
                                "package_sets": ["build"],
                            },
                        ],
                    },
                ),
                mock.call.save_task_id(1234),
                mock.call.watch_task(1234, mock.ANY),
                mock.call.koji_proxy.getTaskResult(1234),
                mock.call.koji_proxy.getBuild(build_id),
                mock.call.koji_proxy.listArchives(buildID=build_id),
            ],
        )

        # Assert there are 2 images added to manifest and the arguments are sane
        self.assertEqual(
            self.compose.im.add.call_args_list,
            [
                mock.call(arch="aarch64", variant="Everything", image=mock.ANY),
                mock.call(arch="x86_64", variant="Everything", image=mock.ANY),
            ],
        )
        for call in self.compose.im.add.call_args_list:
            _, kwargs = call
            image = kwargs["image"]
            self.assertEqual(kwargs["variant"], "Everything")
            self.assertIn(kwargs["arch"], ("aarch64", "x86_64"))
            self.assertEqual(kwargs["arch"], image.arch)
            self.assertEqual(
                "Everything/%(arch)s/images/disk.%(arch)s.qcow2" % {"arch": image.arch},
                image.path,
            )
            self.assertEqual("qcow2", image.format)
            self.assertEqual("qcow2", image.type)
            self.assertEqual("Everything", image.subvariant)

        self.assertTrue(
            os.path.isdir(self.topdir + "/compose/Everything/aarch64/images")
        )
        self.assertTrue(
            os.path.isdir(self.topdir + "/compose/Everything/x86_64/images")
        )

        self.assertEqual(
            Linker.return_value.mock_calls,
            [
                mock.call.link(
                    "/mnt/koji/packages/test-image/1/1/images/disk.%(arch)s.qcow2"
                    % {"arch": arch},
                    self.topdir
                    + "/compose/Everything/%(arch)s/images/disk.%(arch)s.qcow2"
                    % {"arch": arch},
                    link_type="hardlink-or-copy",
                )
                for arch in ["aarch64", "x86_64"]
            ],
        )

    @mock.patch("pungi.util.get_file_size", new=lambda fp: 65536)
    @mock.patch("pungi.util.get_mtime", new=lambda fp: 1024)
    @mock.patch("pungi.phases.osbuild.Linker")
    @mock.patch("pungi.phases.osbuild.kojiwrapper.KojiWrapper")
    def test_process_ostree(self, KojiWrapper, Linker):
        cfg = {
            "name": "test-image",
            "distro": "rhel-8",
            "image_types": ["edge-raw-disk"],
            "ostree_url": "http://edge.example.com/repo",
            "ostree_ref": "test/iot",
            "ostree_parent": "test/iot-parent",
        }
        build_id = 5678
        koji = KojiWrapper.return_value
        koji.watch_task.side_effect = self.make_fake_watch(0)
        koji.koji_proxy.osbuildImage.return_value = 1234
        koji.koji_proxy.getTaskResult.return_value = {
            "composer": {"server": "https://composer.osbuild.org", "id": ""},
            "koji": {"build": build_id},
        }
        koji.koji_proxy.getBuild.return_value = {
            "build_id": build_id,
            "name": "test-image",
            "version": "1",
            "release": "1",
        }
        koji.koji_proxy.listArchives.return_value = [
            {
                "extra": {"image": {"arch": "aarch64"}},
                "filename": "image.aarch64.raw.xz",
                "type_name": "raw-xz",
            },
            {
                "extra": {"image": {"arch": "x86_64"}},
                "filename": "image.x86_64.raw.xz",
                "type_name": "raw-xz",
            },
        ]
        koji.koji_module.pathinfo = orig_koji.pathinfo

        self.t.process(
            (
                self.compose,
                self.compose.variants["Everything"],
                cfg,
                ["aarch64", "x86_64"],
                "1",  # version
                "15",  # release
                "image-target",
                [self.topdir + "/compose/Everything/$arch/os"],
                ["x86_64"],
            ),
            1,
        )

        # Verify two Koji instances were created.
        self.assertEqual(len(KojiWrapper.call_args), 2)
        # Verify correct calls to Koji
        self.assertEqual(
            koji.mock_calls,
            [
                mock.call.login(),
                mock.call.koji_proxy.osbuildImage(
                    "test-image",
                    "1",
                    "rhel-8",
                    ["edge-raw-disk"],
                    "image-target",
                    ["aarch64", "x86_64"],
                    opts={
                        "release": "15",
                        "repo": [self.topdir + "/compose/Everything/$arch/os"],
                        "ostree": {
                            "url": "http://edge.example.com/repo",
                            "ref": "test/iot",
                            "parent": "test/iot-parent",
                        },
                    },
                ),
                mock.call.save_task_id(1234),
                mock.call.watch_task(1234, mock.ANY),
                mock.call.koji_proxy.getTaskResult(1234),
                mock.call.koji_proxy.getBuild(build_id),
                mock.call.koji_proxy.listArchives(buildID=build_id),
            ],
        )

        # Assert there are 2 images added to manifest and the arguments are sane
        self.assertEqual(
            self.compose.im.add.call_args_list,
            [
                mock.call(arch="aarch64", variant="Everything", image=mock.ANY),
                mock.call(arch="x86_64", variant="Everything", image=mock.ANY),
            ],
        )
        for call in self.compose.im.add.call_args_list:
            _, kwargs = call
            image = kwargs["image"]
            self.assertEqual(kwargs["variant"], "Everything")
            self.assertIn(kwargs["arch"], ("aarch64", "x86_64"))
            self.assertEqual(kwargs["arch"], image.arch)
            self.assertEqual(
                "Everything/%(arch)s/images/image.%(arch)s.raw.xz"
                % {"arch": image.arch},
                image.path,
            )
            self.assertEqual("raw.xz", image.format)
            self.assertEqual("raw-xz", image.type)
            self.assertEqual("Everything", image.subvariant)

        self.assertTrue(
            os.path.isdir(self.topdir + "/compose/Everything/aarch64/images")
        )
        self.assertTrue(
            os.path.isdir(self.topdir + "/compose/Everything/x86_64/images")
        )

        self.assertEqual(
            Linker.return_value.mock_calls,
            [
                mock.call.link(
                    "/mnt/koji/packages/test-image/1/1/images/image.%(arch)s.raw.xz"
                    % {"arch": arch},
                    self.topdir
                    + "/compose/Everything/%(arch)s/images/image.%(arch)s.raw.xz"
                    % {"arch": arch},
                    link_type="hardlink-or-copy",
                )
                for arch in ["aarch64", "x86_64"]
            ],
        )

    @mock.patch("pungi.util.get_file_size", new=lambda fp: 65536)
    @mock.patch("pungi.util.get_mtime", new=lambda fp: 1024)
    @mock.patch("pungi.phases.osbuild.Linker")
    @mock.patch("pungi.phases.osbuild.kojiwrapper.KojiWrapper")
    def test_process_upload_options(self, KojiWrapper, Linker):
        cfg = {
            "name": "test-image",
            "distro": "rhel-8",
            "image_types": ["rhel-ec2"],
            "upload_options": {
                "region": "us-east-1",
                "share_with_accounts": ["123456789012"],
            },
        }
        build_id = 5678
        koji = KojiWrapper.return_value
        koji.watch_task.side_effect = self.make_fake_watch(0)
        koji.koji_proxy.osbuildImage.return_value = 1234
        koji.koji_proxy.getTaskResult.return_value = {
            "composer": {"server": "https://composer.osbuild.org", "id": ""},
            "koji": {"build": build_id},
        }
        koji.koji_proxy.getBuild.return_value = {
            "build_id": build_id,
            "name": "test-image",
            "version": "1",
            "release": "1",
        }
        koji.koji_proxy.listArchives.return_value = [
            {
                "extra": {"image": {"arch": "x86_64"}},
                "filename": "image.raw.xz",
                "type_name": "raw-xz",
            }
        ]
        koji.koji_module.pathinfo = orig_koji.pathinfo

        self.t.process(
            (
                self.compose,
                self.compose.variants["Everything"],
                cfg,
                ["x86_64"],
                "1",  # version
                "15",  # release
                "image-target",
                [self.topdir + "/compose/Everything/$arch/os"],
                ["x86_64"],
            ),
            1,
        )

        # Verify two Koji instances were created.
        self.assertEqual(len(KojiWrapper.call_args), 2)
        # Verify correct calls to Koji
        self.assertEqual(
            koji.mock_calls,
            [
                mock.call.login(),
                mock.call.koji_proxy.osbuildImage(
                    "test-image",
                    "1",
                    "rhel-8",
                    ["rhel-ec2"],
                    "image-target",
                    ["x86_64"],
                    opts={
                        "release": "15",
                        "repo": [self.topdir + "/compose/Everything/$arch/os"],
                        "upload_options": {
                            "region": "us-east-1",
                            "share_with_accounts": ["123456789012"],
                        },
                    },
                ),
                mock.call.save_task_id(1234),
                mock.call.watch_task(1234, mock.ANY),
                mock.call.koji_proxy.getTaskResult(1234),
                mock.call.koji_proxy.getBuild(build_id),
                mock.call.koji_proxy.listArchives(buildID=build_id),
            ],
        )

        # Assert there is one image added to manifest and the arguments are sane
        self.assertEqual(
            self.compose.im.add.call_args_list,
            [
                mock.call(arch="x86_64", variant="Everything", image=mock.ANY),
            ],
        )
        for call in self.compose.im.add.call_args_list:
            _, kwargs = call
            image = kwargs["image"]
            self.assertEqual(kwargs["variant"], "Everything")
            self.assertIn(kwargs["arch"], ("x86_64"))
            self.assertEqual(kwargs["arch"], image.arch)
            self.assertEqual(
                "Everything/x86_64/images/image.raw.xz",
                image.path,
            )
            self.assertEqual("raw.xz", image.format)
            self.assertEqual("raw-xz", image.type)
            self.assertEqual("Everything", image.subvariant)

        self.assertTrue(
            os.path.isdir(self.topdir + "/compose/Everything/x86_64/images")
        )

        self.assertEqual(
            Linker.return_value.mock_calls,
            [
                mock.call.link(
                    "/mnt/koji/packages/test-image/1/1/images/image.raw.xz",
                    self.topdir + "/compose/Everything/x86_64/images/image.raw.xz",
                    link_type="hardlink-or-copy",
                )
            ],
        )

    @mock.patch("pungi.util.get_file_size", new=lambda fp: 65536)
    @mock.patch("pungi.util.get_mtime", new=lambda fp: 1024)
    @mock.patch("pungi.phases.osbuild.Linker")
    @mock.patch("pungi.phases.osbuild.kojiwrapper.KojiWrapper")
    def test_process_without_release(self, KojiWrapper, Linker):
        cfg = {"name": "test-image", "distro": "rhel-8", "image_types": ["qcow2"]}
        build_id = 5678
        koji = KojiWrapper.return_value
        koji.watch_task.side_effect = self.make_fake_watch(0)
        koji.koji_proxy.osbuildImage.return_value = 1234
        koji.koji_proxy.getTaskResult.return_value = {
            "composer": {"server": "https://composer.osbuild.org", "id": ""},
            "koji": {"build": build_id},
        }
        koji.koji_proxy.getBuild.return_value = {
            "build_id": build_id,
            "name": "test-image",
            "version": "1",
            "release": "1",
        }
        koji.koji_proxy.listArchives.return_value = [
            {
                "extra": {"image": {"arch": "aarch64"}},
                "filename": "disk.aarch64.qcow2",
                "type_name": "qcow2",
            },
            {
                "extra": {"image": {"arch": "x86_64"}},
                "filename": "disk.x86_64.qcow2",
                "type_name": "qcow2",
            },
        ]
        koji.koji_module.pathinfo = orig_koji.pathinfo

        self.t.process(
            (
                self.compose,
                self.compose.variants["Everything"],
                cfg,
                ["aarch64", "x86_64"],
                "1",
                None,
                "image-target",
                [self.topdir + "/compose/Everything/$arch/os"],
                ["x86_64"],
            ),
            1,
        )

        # Verify two Koji instances were created.
        self.assertEqual(len(KojiWrapper.call_args), 2)
        # Verify correct calls to Koji
        self.assertEqual(
            koji.mock_calls,
            [
                mock.call.login(),
                mock.call.koji_proxy.osbuildImage(
                    "test-image",
                    "1",
                    "rhel-8",
                    ["qcow2"],
                    "image-target",
                    ["aarch64", "x86_64"],
                    opts={"repo": [self.topdir + "/compose/Everything/$arch/os"]},
                ),
                mock.call.save_task_id(1234),
                mock.call.watch_task(1234, mock.ANY),
                mock.call.koji_proxy.getTaskResult(1234),
                mock.call.koji_proxy.getBuild(build_id),
                mock.call.koji_proxy.listArchives(buildID=build_id),
            ],
        )

        # Assert there are 2 images added to manifest and the arguments are sane
        self.assertEqual(
            self.compose.im.add.call_args_list,
            [
                mock.call(arch="aarch64", variant="Everything", image=mock.ANY),
                mock.call(arch="x86_64", variant="Everything", image=mock.ANY),
            ],
        )
        for call in self.compose.im.add.call_args_list:
            _, kwargs = call
            image = kwargs["image"]
            self.assertEqual(kwargs["variant"], "Everything")
            self.assertIn(kwargs["arch"], ("aarch64", "x86_64"))
            self.assertEqual(kwargs["arch"], image.arch)
            self.assertEqual(
                "Everything/%(arch)s/images/disk.%(arch)s.qcow2" % {"arch": image.arch},
                image.path,
            )
            self.assertEqual("qcow2", image.format)
            self.assertEqual("qcow2", image.type)
            self.assertEqual("Everything", image.subvariant)

        self.assertTrue(
            os.path.isdir(self.topdir + "/compose/Everything/aarch64/images")
        )
        self.assertTrue(
            os.path.isdir(self.topdir + "/compose/Everything/x86_64/images")
        )

        self.assertEqual(
            Linker.return_value.mock_calls,
            [
                mock.call.link(
                    "/mnt/koji/packages/test-image/1/1/images/disk.%(arch)s.qcow2"
                    % {"arch": arch},
                    self.topdir
                    + "/compose/Everything/%(arch)s/images/disk.%(arch)s.qcow2"
                    % {"arch": arch},
                    link_type="hardlink-or-copy",
                )
                for arch in ["aarch64", "x86_64"]
            ],
        )

    @mock.patch("pungi.phases.osbuild.kojiwrapper.KojiWrapper")
    def test_task_fails(self, KojiWrapper):
        cfg = {"name": "test-image", "distro": "rhel-8", "image_types": ["qcow2"]}
        koji = KojiWrapper.return_value
        koji.watch_task.side_effect = self.make_fake_watch(1)
        koji.koji_proxy.osbuildImage.return_value = 1234

        with self.assertRaises(RuntimeError):
            self.t.process(
                (
                    self.compose,
                    self.compose.variants["Everything"],
                    cfg,
                    ["aarch64", "x86_64"],
                    "1",
                    None,
                    "image-target",
                    [self.topdir + "/compose/Everything/$arch/os"],
                    False,
                ),
                1,
            )

    @mock.patch("pungi.phases.osbuild.kojiwrapper.KojiWrapper")
    def test_task_fails_but_is_failable(self, KojiWrapper):
        cfg = {
            "name": "test-image",
            "distro": "rhel-8",
            "image_types": ["qcow2"],
            "failable": ["x86_65"],
        }
        koji = KojiWrapper.return_value
        koji.watch_task.side_effect = self.make_fake_watch(1)
        koji.koji_proxy.osbuildImage.return_value = 1234

        self.t.process(
            (
                self.compose,
                self.compose.variants["Everything"],
                cfg,
                ["aarch64", "x86_64"],
                "1",
                None,
                "image-target",
                [self.topdir + "/compose/Everything/$arch/os"],
                True,
            ),
            1,
        )

        self.assertFalse(
            os.path.isdir(self.topdir + "/compose/Everything/aarch64/images")
        )
        self.assertFalse(
            os.path.isdir(self.topdir + "/compose/Everything/x86_64/images")
        )
        self.assertEqual(len(self.compose.im.add.call_args_list), 0)
