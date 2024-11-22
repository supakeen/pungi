# -*- coding: utf-8 -*-

import os
from io import StringIO
from unittest import mock

from parameterized import parameterized

from tests import helpers
from pungi import createiso


class CreateIsoScriptTest(helpers.PungiTestCase):
    def setUp(self):
        super(CreateIsoScriptTest, self).setUp()
        self.outdir = os.path.join(self.topdir, "isos")
        self.out = StringIO()
        self.maxDiff = None

    def assertScript(self, cmds):
        script = self.out.getvalue().strip().split("\n")
        self.assertEqual(script[:3], ["#!/bin/bash", "set -ex", "cd %s" % self.outdir])
        self.assertEqual(script[3:], cmds)

    def test_minimal_run(self):
        createiso.write_script(
            createiso.CreateIsoOpts(
                output_dir=self.outdir,
                iso_name="DP-1.0-20160405.t.3-x86_64.iso",
                volid="DP-1.0-20160405.t.3",
                graft_points="graft-list",
                arch="x86_64",
            ),
            self.out,
        )
        self.assertScript(
            [
                " ".join(
                    [
                        "/usr/bin/genisoimage",
                        "-untranslated-filenames",
                        "-volid",
                        "DP-1.0-20160405.t.3",
                        "-J",
                        "-joliet-long",
                        "-rational-rock",
                        "-translation-table",
                        "-input-charset",
                        "utf-8",
                        "-x",
                        "./lost+found",
                        "-o",
                        "DP-1.0-20160405.t.3-x86_64.iso",
                        "-graft-points",
                        "-path-list",
                        "graft-list",
                    ]
                ),
                " ".join(["/usr/bin/implantisomd5", "DP-1.0-20160405.t.3-x86_64.iso"]),
                "isoinfo -R -f -i DP-1.0-20160405.t.3-x86_64.iso | grep -v '/TRANS.TBL$' | sort >> DP-1.0-20160405.t.3-x86_64.iso.manifest",  # noqa: E501
            ]
        )

    def test_bootable_run(self):
        createiso.write_script(
            createiso.CreateIsoOpts(
                output_dir=self.outdir,
                iso_name="DP-1.0-20160405.t.3-x86_64.iso",
                volid="DP-1.0-20160405.t.3",
                graft_points="graft-list",
                arch="x86_64",
                buildinstall_method="lorax",
            ),
            self.out,
        )

        self.assertScript(
            [
                createiso.FIND_TEMPLATE_SNIPPET,
                " ".join(
                    [
                        "/usr/bin/genisoimage",
                        "-untranslated-filenames",
                        "-volid",
                        "DP-1.0-20160405.t.3",
                        "-J",
                        "-joliet-long",
                        "-rational-rock",
                        "-translation-table",
                        "-input-charset",
                        "utf-8",
                        "-x",
                        "./lost+found",
                        "-b",
                        "isolinux/isolinux.bin",
                        "-c",
                        "isolinux/boot.cat",
                        "-no-emul-boot",
                        "-boot-load-size",
                        "4",
                        "-boot-info-table",
                        "-eltorito-alt-boot",
                        "-e",
                        "images/efiboot.img",
                        "-no-emul-boot",
                        "-o",
                        "DP-1.0-20160405.t.3-x86_64.iso",
                        "-graft-points",
                        "-path-list",
                        "graft-list",
                    ]
                ),
                " ".join(
                    ["/usr/bin/isohybrid", "--uefi", "DP-1.0-20160405.t.3-x86_64.iso"]
                ),
                " ".join(["/usr/bin/implantisomd5", "DP-1.0-20160405.t.3-x86_64.iso"]),
                "isoinfo -R -f -i DP-1.0-20160405.t.3-x86_64.iso | grep -v '/TRANS.TBL$' | sort >> DP-1.0-20160405.t.3-x86_64.iso.manifest",  # noqa: E501
            ]
        )

    def test_bootable_run_on_i386(self):
        # This will call isohybrid, but not with --uefi switch
        createiso.write_script(
            createiso.CreateIsoOpts(
                output_dir=self.outdir,
                iso_name="DP-1.0-20160405.t.3-i386.iso",
                volid="DP-1.0-20160405.t.3",
                graft_points="graft-list",
                arch="i386",
                buildinstall_method="lorax",
            ),
            self.out,
        )

        self.assertScript(
            [
                createiso.FIND_TEMPLATE_SNIPPET,
                " ".join(
                    [
                        "/usr/bin/genisoimage",
                        "-untranslated-filenames",
                        "-volid",
                        "DP-1.0-20160405.t.3",
                        "-J",
                        "-joliet-long",
                        "-rational-rock",
                        "-translation-table",
                        "-input-charset",
                        "utf-8",
                        "-x",
                        "./lost+found",
                        "-b",
                        "isolinux/isolinux.bin",
                        "-c",
                        "isolinux/boot.cat",
                        "-no-emul-boot",
                        "-boot-load-size",
                        "4",
                        "-boot-info-table",
                        "-o",
                        "DP-1.0-20160405.t.3-i386.iso",
                        "-graft-points",
                        "-path-list",
                        "graft-list",
                    ]
                ),
                " ".join(["/usr/bin/isohybrid", "DP-1.0-20160405.t.3-i386.iso"]),
                " ".join(["/usr/bin/implantisomd5", "DP-1.0-20160405.t.3-i386.iso"]),
                "isoinfo -R -f -i DP-1.0-20160405.t.3-i386.iso | grep -v '/TRANS.TBL$' | sort >> DP-1.0-20160405.t.3-i386.iso.manifest",  # noqa: E501
            ]
        )

    def test_bootable_run_ppc64(self):
        createiso.write_script(
            createiso.CreateIsoOpts(
                output_dir=self.outdir,
                iso_name="DP-1.0-20160405.t.3-ppc64.iso",
                volid="DP-1.0-20160405.t.3",
                graft_points="graft-list",
                arch="ppc64",
                buildinstall_method="lorax",
            ),
            self.out,
        )

        self.assertScript(
            [
                createiso.FIND_TEMPLATE_SNIPPET,
                " ".join(
                    [
                        "/usr/bin/genisoimage",
                        "-untranslated-filenames",
                        "-volid",
                        "DP-1.0-20160405.t.3",
                        "-J",
                        "-joliet-long",
                        "-rational-rock",
                        "-translation-table",
                        "-x",
                        "./lost+found",
                        "-part",
                        "-hfs",
                        "-r",
                        "-l",
                        "-sysid",
                        "PPC",
                        "-no-desktop",
                        "-allow-multidot",
                        "-chrp-boot",
                        "-map",
                        "$TEMPLATE/config_files/ppc/mapping",
                        "-hfs-bless",
                        "/ppc/mac",
                        "-o",
                        "DP-1.0-20160405.t.3-ppc64.iso",
                        "-graft-points",
                        "-path-list",
                        "graft-list",
                    ]
                ),
                " ".join(["/usr/bin/implantisomd5", "DP-1.0-20160405.t.3-ppc64.iso"]),
                "isoinfo -R -f -i DP-1.0-20160405.t.3-ppc64.iso | grep -v '/TRANS.TBL$' | sort >> DP-1.0-20160405.t.3-ppc64.iso.manifest",  # noqa: E501
            ]
        )

    def test_bootable_run_on_s390x(self):
        createiso.write_script(
            createiso.CreateIsoOpts(
                output_dir=self.outdir,
                iso_name="DP-1.0-20160405.t.3-s390x.iso",
                volid="DP-1.0-20160405.t.3",
                graft_points="graft-list",
                arch="s390x",
                buildinstall_method="lorax",
            ),
            self.out,
        )

        self.assertScript(
            [
                createiso.FIND_TEMPLATE_SNIPPET,
                " ".join(
                    [
                        "/usr/bin/genisoimage",
                        "-untranslated-filenames",
                        "-volid",
                        "DP-1.0-20160405.t.3",
                        "-J",
                        "-joliet-long",
                        "-rational-rock",
                        "-translation-table",
                        "-input-charset",
                        "utf-8",
                        "-x",
                        "./lost+found",
                        "-eltorito-boot images/cdboot.img",
                        "-no-emul-boot",
                        "-o",
                        "DP-1.0-20160405.t.3-s390x.iso",
                        "-graft-points",
                        "-path-list",
                        "graft-list",
                    ]
                ),
                " ".join(["/usr/bin/implantisomd5", "DP-1.0-20160405.t.3-s390x.iso"]),
                "isoinfo -R -f -i DP-1.0-20160405.t.3-s390x.iso | grep -v '/TRANS.TBL$' | sort >> DP-1.0-20160405.t.3-s390x.iso.manifest",  # noqa: E501
            ]
        )

    @mock.patch("sys.stderr")
    @mock.patch("kobo.shortcuts.run")
    def test_run_with_jigdo_bad_args(self, run, stderr):
        with self.assertRaises(RuntimeError):
            createiso.write_script(
                createiso.CreateIsoOpts(
                    output_dir=self.outdir,
                    iso_name="DP-1.0-20160405.t.3-x86_64.iso",
                    volid="DP-1.0-20160405.t.3",
                    graft_points="graft-list",
                    arch="x86_64",
                    jigdo_dir="%s/jigdo" % self.topdir,
                ),
                self.out,
            )

    @mock.patch("kobo.shortcuts.run")
    def test_run_with_jigdo(self, run):
        createiso.write_script(
            createiso.CreateIsoOpts(
                output_dir=self.outdir,
                iso_name="DP-1.0-20160405.t.3-x86_64.iso",
                volid="DP-1.0-20160405.t.3",
                graft_points="graft-list",
                arch="x86_64",
                jigdo_dir="%s/jigdo" % self.topdir,
                os_tree="%s/os" % self.topdir,
            ),
            self.out,
        )

        self.assertScript(
            [
                " ".join(
                    [
                        "/usr/bin/genisoimage",
                        "-untranslated-filenames",
                        "-volid",
                        "DP-1.0-20160405.t.3",
                        "-J",
                        "-joliet-long",
                        "-rational-rock",
                        "-translation-table",
                        "-input-charset",
                        "utf-8",
                        "-x",
                        "./lost+found",
                        "-o",
                        "DP-1.0-20160405.t.3-x86_64.iso",
                        "-graft-points",
                        "-path-list",
                        "graft-list",
                    ]
                ),
                " ".join(["/usr/bin/implantisomd5", "DP-1.0-20160405.t.3-x86_64.iso"]),
                "isoinfo -R -f -i DP-1.0-20160405.t.3-x86_64.iso | grep -v '/TRANS.TBL$' | sort >> DP-1.0-20160405.t.3-x86_64.iso.manifest",  # noqa: E501
                " ".join(
                    [
                        "jigdo-file",
                        "make-template",
                        "--force",
                        "--image=%s/isos/DP-1.0-20160405.t.3-x86_64.iso" % self.topdir,
                        "--jigdo=%s/jigdo/DP-1.0-20160405.t.3-x86_64.iso.jigdo"
                        % self.topdir,
                        "--template=%s/jigdo/DP-1.0-20160405.t.3-x86_64.iso.template"
                        % self.topdir,
                        "--no-servers-section",
                        "--report=noprogress",
                        self.topdir + "/os//",
                    ]
                ),
            ]
        )

    @parameterized.expand(
        [("644", 0o644), ("664", 0o664), ("666", 0o666), ("2644", 0o2644)]
    )
    def test_get_perms_non_executable(self, test_name, mode):
        path = helpers.touch(os.path.join(self.topdir, "f"), mode=mode)
        self.assertEqual(createiso._get_perms(path), 0o444)

    @parameterized.expand(
        [
            ("544", 0o544),
            ("554", 0o554),
            ("555", 0o555),
            ("744", 0o744),
            ("755", 0o755),
            ("774", 0o774),
            ("775", 0o775),
            ("777", 0o777),
            ("2775", 0o2775),
        ]
    )
    def test_get_perms_executable(self, test_name, mode):
        path = helpers.touch(os.path.join(self.topdir, "f"), mode=mode)
        self.assertEqual(createiso._get_perms(path), 0o555)
