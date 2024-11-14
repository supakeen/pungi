# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <https://gnu.org/licenses/>.

from __future__ import absolute_import
from __future__ import print_function

import os
import sys

from argparse import ArgumentParser, Action

from pungi import get_full_version
import pungi.gather
import pungi.config
import pungi.ks


def get_arguments(config):
    parser = ArgumentParser()

    class SetConfig(Action):
        def __call__(self, parser, namespace, value, option_string=None):
            config.set("pungi", self.dest, value)

    parser.add_argument("--version", action="version", version=get_full_version())

    # Pulled in from config file to be cli options as part of pykickstart conversion
    parser.add_argument(
        "--destdir",
        dest="destdir",
        action=SetConfig,
        help="destination directory (defaults to current directory)",
    )
    parser.add_argument(
        "--cachedir",
        dest="cachedir",
        action=SetConfig,
        help="package cache directory (defaults to /var/cache/pungi)",
    )
    parser.add_argument(
        "--selfhosting",
        action="store_true",
        dest="selfhosting",
        help="build a self-hosting tree by following build dependencies (optional)",
    )
    parser.add_argument(
        "--fulltree",
        action="store_true",
        dest="fulltree",
        help="build a tree that includes all packages built from corresponding source rpms (optional)",  # noqa: E501
    )
    parser.add_argument(
        "--nosource",
        action="store_true",
        dest="nosource",
        help="disable gathering of source packages (optional)",
    )
    parser.add_argument(
        "--nodebuginfo",
        action="store_true",
        dest="nodebuginfo",
        help="disable gathering of debuginfo packages (optional)",
    )
    parser.add_argument(
        "--nodownload",
        action="store_true",
        dest="nodownload",
        help="disable downloading of packages. instead, print the package URLs (optional)",  # noqa: E501
    )
    parser.add_argument(
        "--nogreedy",
        action="store_true",
        dest="nogreedy",
        help="disable pulling of all providers of package dependencies (optional)",
    )
    parser.add_argument(
        "--nodeps",
        action="store_false",
        dest="resolve_deps",
        default=True,
        help="disable resolving dependencies",
    )
    parser.add_argument(
        "--force",
        default=False,
        action="store_true",
        help="Force reuse of an existing destination directory (will overwrite files)",
    )
    parser.add_argument(
        "--nohash",
        default=False,
        action="store_true",
        help="disable hashing the Packages trees",
    )
    parser.add_argument(
        "--full-archlist",
        action="store_true",
        help="Use the full arch list for x86_64 (include i686, i386, etc.)",
    )
    parser.add_argument("--arch", help="Override default (uname based) arch")
    parser.add_argument(
        "--greedy", metavar="METHOD", help="Greedy method; none, all, build"
    )
    parser.add_argument(
        "--multilib",
        action="append",
        metavar="METHOD",
        help="Multilib method; can be specified multiple times; recommended: devel, runtime",  # noqa: E501
    )
    parser.add_argument(
        "--lookaside-repo",
        action="append",
        dest="lookaside_repos",
        metavar="NAME",
        help="Specify lookaside repo name(s) (packages will used for depsolving but not be included in the output)",  # noqa: E501
    )
    parser.add_argument(
        "--workdirbase",
        dest="workdirbase",
        action=SetConfig,
        help="base working directory (defaults to destdir + /work)",
    )
    parser.add_argument(
        "--no-dvd",
        default=False,
        action="store_true",
        dest="no_dvd",
        help="Do not make a install DVD/CD only the netinstall image and the tree",
    )
    parser.add_argument("--lorax-conf", help="Path to lorax.conf file (optional)")
    parser.add_argument(
        "-i",
        "--installpkgs",
        default=[],
        action="append",
        metavar="STRING",
        help="Package glob for lorax to install before runtime-install.tmpl runs. (may be listed multiple times)",  # noqa: E501
    )
    parser.add_argument(
        "--multilibconf",
        default=None,
        action=SetConfig,
        help="Path to multilib conf files. Default is /usr/share/pungi/multilib/",
    )

    parser.add_argument(
        "-c",
        "--config",
        dest="config",
        required=True,
        help="Path to kickstart config file",
    )
    parser.add_argument(
        "-G",
        action="store_true",
        default=False,
        dest="do_gather",
        help="Flag to enable processing the Gather stage",
    )

    parser.add_argument(
        "--pungirc",
        dest="pungirc",
        default="~/.pungirc",
        action=SetConfig,
        help="Read pungi options from config file ",
    )

    return parser.parse_args()


def main():
    config = pungi.config.Config()
    opts = get_arguments(config)

    # Read the config to create "new" defaults
    # reparse command line options so they take precedence
    config = pungi.config.Config(pungirc=opts.pungirc)
    opts = get_arguments(config)

    # Set up the kickstart parser and pass in the kickstart file we were handed
    ksparser = pungi.ks.get_ksparser(ks_path=opts.config)

    config.set("pungi", "force", str(opts.force))

    if config.get("pungi", "workdirbase") == "/work":
        config.set("pungi", "workdirbase", "%s/work" % config.get("pungi", "destdir"))
    # Set up our directories
    if not os.path.exists(config.get("pungi", "destdir")):
        try:
            os.makedirs(config.get("pungi", "destdir"))
        except OSError:
            print(
                "Error: Cannot create destination dir %s"
                % config.get("pungi", "destdir"),
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        print("Warning: Reusing existing destination directory.")

    if not os.path.exists(config.get("pungi", "workdirbase")):
        try:
            os.makedirs(config.get("pungi", "workdirbase"))
        except OSError:
            print(
                "Error: Cannot create working base dir %s"
                % config.get("pungi", "workdirbase"),
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        print("Warning: Reusing existing working base directory.")

    cachedir = config.get("pungi", "cachedir")

    if not os.path.exists(cachedir):
        try:
            os.makedirs(cachedir)
        except OSError:
            print("Error: Cannot create cache dir %s" % cachedir, file=sys.stderr)
            sys.exit(1)

    # Set debuginfo flag
    if opts.nodebuginfo:
        config.set("pungi", "debuginfo", "False")
    if opts.greedy:
        config.set("pungi", "greedy", opts.greedy)
    else:
        # XXX: compatibility
        if opts.nogreedy:
            config.set("pungi", "greedy", "none")
        else:
            config.set("pungi", "greedy", "all")
    config.set("pungi", "resolve_deps", str(bool(opts.resolve_deps)))
    if opts.nohash:
        config.set("pungi", "nohash", "True")
    if opts.full_archlist:
        config.set("pungi", "full_archlist", "True")
    if opts.arch:
        config.set("pungi", "arch", opts.arch)
    if opts.multilib:
        config.set("pungi", "multilib", " ".join(opts.multilib))
    if opts.lookaside_repos:
        config.set("pungi", "lookaside_repos", " ".join(opts.lookaside_repos))
    config.set("pungi", "fulltree", str(bool(opts.fulltree)))
    config.set("pungi", "selfhosting", str(bool(opts.selfhosting)))
    config.set("pungi", "nosource", str(bool(opts.nosource)))
    config.set("pungi", "nodebuginfo", str(bool(opts.nodebuginfo)))

    # Actually do work.
    mypungi = pungi.gather.Pungi(config, ksparser)

    with mypungi.yumlock:
        mypungi._inityum()  # initialize the yum object for things that need it
        mypungi.gather()
        if opts.nodownload:
            for line in mypungi.list_packages():
                flags_str = ",".join(line["flags"])
                if flags_str:
                    flags_str = "(%s)" % flags_str
                sys.stdout.write("RPM%s: %s\n" % (flags_str, line["path"]))
            sys.stdout.flush()
        else:
            mypungi.downloadPackages()
        mypungi.makeCompsFile()
        if not opts.nodebuginfo:
            mypungi.getDebuginfoList()
            if opts.nodownload:
                for line in mypungi.list_debuginfo():
                    flags_str = ",".join(line["flags"])
                    if flags_str:
                        flags_str = "(%s)" % flags_str
                    sys.stdout.write("DEBUGINFO%s: %s\n" % (flags_str, line["path"]))
                sys.stdout.flush()
            else:
                mypungi.downloadDebuginfo()
        if not opts.nosource:
            if opts.nodownload:
                for line in mypungi.list_srpms():
                    flags_str = ",".join(line["flags"])
                    if flags_str:
                        flags_str = "(%s)" % flags_str
                    sys.stdout.write("SRPM%s: %s\n" % (flags_str, line["path"]))
                sys.stdout.flush()
            else:
                mypungi.downloadSRPMs()

        print("RPM size:       %s MiB" % (mypungi.size_packages() / 1024**2))
        if not opts.nodebuginfo:
            print("DEBUGINFO size: %s MiB" % (mypungi.size_debuginfo() / 1024**2))
        if not opts.nosource:
            print("SRPM size:      %s MiB" % (mypungi.size_srpms() / 1024**2))

    print("All done!")
