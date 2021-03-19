"""rpmrepo - utilities

A module with a wide array of different utility functions that extend the
standard library.
"""

# pylint: disable=invalid-name

import contextlib
import errno
import os


@contextlib.contextmanager
def suppress_oserror(*errnos):
    """Suppress OSError Exceptions

    This is an extension to `contextlib.suppress()` from the python standard
    library. It catches any `OSError` exceptions and suppresses them. However,
    it only catches the exceptions that match the specified error numbers.

    Parameters
    ----------
    errnos
        A list of error numbers to match on. If none are specified, this
        function has no effect.
    """

    try:
        yield
    except OSError as e:
        if e.errno not in errnos:
            raise e


@contextlib.contextmanager
def open_tmpfile(dirpath, mode=0o777):
    """Open O_TMPFILE and optionally link it

    This opens a new temporary file in the specified directory. As part of the
    context-manager, a dictionary is returned as the context object. An opened
    stream to the temporary file is accessible as `ctx["stream"]`.

    If the caller sets `ctx["name"]` to something else than `None`, the file
    will be attempted to be linked as that name once the context is exited. If
    `ctx["replace"]` is changed to `True`, a possible previous file is
    replaced. If it is set to `False`, the operation fails if there is a
    previous file with the same name.

    Parameters
    ----------
    dirpath
        A path to a directory where to open the temporary file in.
    mode
        The file mode to use when opening the temporary file. Note that this is
        subject to the OS `umask`.
    """

    ctx = {"name": None, "replace": False, "stream": None}
    dirfd = None
    fd = None

    try:
        dirfd = os.open(dirpath, os.O_PATH | os.O_CLOEXEC)
        fd = os.open(".", os.O_RDWR | os.O_TMPFILE | os.O_CLOEXEC, mode, dir_fd=dirfd)
        with os.fdopen(fd, "rb+", closefd=False) as stream:
            ctx["stream"] = stream
            yield ctx
        if ctx["name"] is not None:
            if ctx["replace"]:
                # We would want to call:
                #
                #   os.replace(f"/proc/self/fd/{fd}", ctx["name"], dst_dir_fd=dirfd)
                #
                # ..but the underlying linux syscall `renameat2(2)` does not
                # support `AT_SYMLINK_FOLLOW` nor `AT_EMPTY_PATH`, hence we
                # cannot combine it with `O_TMPFILE`. We accept the race for
                # now and wait for the kernel to provide the extended flags.
                with suppress_oserror(errno.ENOENT):
                    os.unlink(ctx["name"], dir_fd=dirfd)
                os.link(f"/proc/self/fd/{fd}", ctx["name"], dst_dir_fd=dirfd)
            else:
                os.link(f"/proc/self/fd/{fd}", ctx["name"], dst_dir_fd=dirfd)
    finally:
        if fd is not None:
            os.close(fd)
        if dirfd is not None:
            os.close(dirfd)
