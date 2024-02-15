# -*- coding: utf-8 -*-


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


import os
import json
import six
from six.moves import shlex_quote


from .base import OSTree
from .utils import tweak_treeconf


def emit(cmd):
    """Print line of shell code into the stream."""
    if isinstance(cmd, six.string_types):
        print(cmd)
    else:
        print(" ".join([shlex_quote(x) for x in cmd]))


class Container(OSTree):
    def _make_container(self):
        """Compose OSTree Container Native image"""
        stamp_file = os.path.join(self.logdir, "%s.stamp" % self.name)
        cmd = [
            "rpm-ostree",
            "compose",
            "image",
            # Always initialize for now
            "--initialize",
            # Touch the file if a new commit was created. This can help us tell
            # if the commitid file is missing because no commit was created or
            # because something went wrong.
            "--touch-if-changed=%s" % stamp_file,
            self.treefile,
        ]
        fullpath = os.path.join(self.path, "%s.ociarchive" % self.name)
        cmd.append(fullpath)

        # Set the umask to be more permissive so directories get group write
        # permissions. See https://pagure.io/releng/issue/8811#comment-629051
        emit("umask 0002")
        emit(cmd)

    def run(self):
        self.name = self.args.name
        self.path = self.args.path
        self.treefile = self.args.treefile
        self.logdir = self.args.log_dir
        self.extra_config = self.args.extra_config

        if self.extra_config:
            self.extra_config = json.load(open(self.extra_config, "r"))
            repos = self.extra_config.get("repo", [])
            keep_original_sources = self.extra_config.get(
                "keep_original_sources", False
            )
        else:
            # missing extra_config mustn't affect tweak_treeconf call
            repos = []
            keep_original_sources = True

        update_dict = {"automatic-version-prefix": self.args.version}

        self.treefile = tweak_treeconf(
            self.treefile,
            source_repos=repos,
            keep_original_sources=keep_original_sources,
            update_dict=update_dict,
        )

        self._make_container()
