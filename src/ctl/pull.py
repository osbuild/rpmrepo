"""rpmrepo - Pull RPM Repository

This module implements the functions that pull an entire RPM repository to
local storage.
"""

# pylint: disable=duplicate-code,invalid-name,too-few-public-methods

import contextlib
import errno
import os
import subprocess
import sys
import tempfile

from . import util


# pylint: disable=too-many-instance-attributes
class Pull(contextlib.AbstractContextManager):
    """Pull RPM repository"""

    def __init__(self, cache, platform_id, baseurl):
        self._baseurl = baseurl
        self._cache = cache
        self._exitstack = None
        self._path_dnfconf = None
        self._path_conf = os.path.join(cache, "conf")
        self._path_repo = os.path.join(cache, "repo")
        self._path_root = None
        self._path_tmp = os.path.join(cache, "tmp")
        self._platform_id = platform_id

    def __enter__(self):
        self._exitstack = contextlib.ExitStack()
        with self._exitstack:
            # Create our scaffolding. Note that the entire `cache` directory is
            # managed by the caller, so we explicitly do not clean it up but
            # support retaining it across calls, if the caller desires.
            os.makedirs(self._path_conf, exist_ok=True)
            os.makedirs(self._path_repo, exist_ok=True)
            os.makedirs(self._path_tmp, exist_ok=True)

            # Create a temporary `root` directory which we then provide to dnf
            # to store any of its state files (they are not really necessary,
            # but `dnf` requires us to provide it).
            path = tempfile.TemporaryDirectory(prefix="root-", dir=self._path_tmp)
            self._path_root = self._exitstack.enter_context(path)

            # Write a `dnf.conf` with just a single repository configuration
            # which we then use for the `dnf reposync` operation.
            with util.open_tmpfile(self._path_conf) as ctx:
                content = (
                    "[main]\n"
                    f"module_platform_id=platform:{self._platform_id}\n"
                    "[repo0]\n"
                    "name=repo0\n"
                    f"baseurl={self._baseurl}\n"
                )
                ctx["stream"].write(content.encode())
                ctx["stream"].flush()
                ctx["name"] = "dnf.conf"
                ctx["replace"] = True
            self._path_dnfconf = os.path.join(self._path_conf, "dnf.conf")

            # Setup succeeded, make sure to retain the exitstack for __exit__.
            self._exitstack = self._exitstack.pop_all()

        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self._exitstack.close()
        self._exitstack = None

    def _run_reposync(self):
        cmd = [
            "dnf", "-v", "reposync",
            "--config", self._path_dnfconf,
            "--download-metadata",
            "--download-path", self._path_repo,
            "--installroot", self._path_root,
            "--norepopath",
            "--setopt", "reposdir=",
            "--setopt", "skip_if_unavailable=false",
        ]

        sys.stdout.flush()
        proc = subprocess.Popen(cmd)
        return proc.wait()

    def pull(self):
        """Run operation"""

        with util.suppress_oserror(errno.ENOENT):
            os.unlink(os.path.join(self._path_conf, "repo.ok"))

        ret = self._run_reposync()
        if ret != 0:
            raise RuntimeError(f"Failed during dnf reposync with exitcode '{ret}'")

        open(os.path.join(self._path_conf, "repo.ok"), "wb").close()
