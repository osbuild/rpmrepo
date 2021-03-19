"""rpmrepo - Create RPM Repository Index

This module creates a custom index for an RPM repository which provides
a content-addressable storage alongside a symlink collection.
"""

# pylint: disable=duplicate-code,invalid-name,too-few-public-methods

import contextlib
import errno
import hashlib
import os
import shutil

from . import util


class Index(contextlib.AbstractContextManager):
    """Create RPM repository Index"""

    def __init__(self, cache):
        self._cache = cache
        self._path_conf = os.path.join(cache, "conf")
        self._path_data = os.path.join(cache, "index/data")
        self._path_index = os.path.join(cache, "index")
        self._path_repo = os.path.join(cache, "repo")
        self._path_snapshot = os.path.join(cache, "index/snapshot")

    def __exit__(self, exc_type, exc_value, exc_tb):
        pass

    @staticmethod
    def _checksum(filp):
        hashproc = hashlib.sha256()
        for block in iter(lambda ctx=filp: ctx.read(4096), b''):
            hashproc.update(block)
        return "sha256-" + hashproc.hexdigest()

    def index(self):
        """Create index of the RPM repository files"""

        #
        # We require a repository to be imported or pulled locally before we
        # can create an index for it.
        #

        assert os.access(os.path.join(self._path_conf, "repo.ok"), os.R_OK)

        #
        # Delete a possible previous index and prepare the scaffolding of the
        # index directory.
        #

        with util.suppress_oserror(errno.ENOENT):
            os.unlink(os.path.join(self._path_conf, "index.ok"))

        if os.path.isdir(self._path_index):
            shutil.rmtree(self._path_index)

        os.mkdir(self._path_index)
        os.mkdir(self._path_data)
        os.mkdir(self._path_snapshot)

        #
        # Create a content-addressed data directory with all files hardlinked
        # from their original location in the `repo` directory. Index them by
        # their checksum.
        # Additionally, create a second snapshot directly that mirrors the
        # repository directory structure but only stores the checksum of each
        # file rather than its contents.
        #

        for level, subdirs, entries in os.walk(self._path_repo):
            levelpath = os.path.relpath(level, self._path_repo)

            for entry in subdirs:
                os.mkdir(os.path.join(self._path_snapshot, levelpath, entry))

            for entry in entries:
                with open(os.path.join(level, entry), "rb") as filp:
                    checksum = self._checksum(filp)

                with open(os.path.join(self._path_snapshot, levelpath, entry), "wb") as filp:
                    filp.write(checksum.encode())

                with util.suppress_oserror(errno.EEXIST):
                    os.link(
                        os.path.join(level, entry),
                        os.path.join(self._path_data, checksum),
                        follow_symlinks=False,
                    )

        open(os.path.join(self._path_conf, "index.ok"), "wb").close()
