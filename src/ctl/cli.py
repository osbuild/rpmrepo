"""rpmrepo - Command Line Interface

The `cli` module provides a command-line interface to the rpmrepo package. It
provides the most basic way to execute and interact with the rpmrepo functions.
"""

# pylint: disable=duplicate-code,invalid-name,too-few-public-methods

import argparse
import contextlib
import os
import sys
import uuid

from . import index, pull, push, enumerate_cache


class CliIndex:
    """Index Command"""

    def __init__(self, ctx):
        self._ctx = ctx

    def run(self):
        """Run index command"""

        with index.Index(self._ctx.cache) as cmd:
            cmd.index()

        return 0


class CliPull:
    """Pull Command"""

    def __init__(self, ctx):
        self._ctx = ctx

    def run(self):
        """Run pull command"""

        with pull.Pull(
                self._ctx.cache,
                self._ctx.args.platform_id,
                self._ctx.args.base_url,
            ) as cmd:
            cmd.pull()

        return 0


class CliPush:
    """Push Command"""

    def __init__(self, ctx):
        self._ctx = ctx

    def _parse_args(self):
        for entry in self._ctx.args.to:
            assert len(entry) == 3
            assert entry[0] in ["data", "snapshot"]
            if entry[0] == "data":
                assert entry[1] in ["public", "rhvpn"]

    def run(self):
        """Run push command"""

        self._parse_args()

        with push.Push(self._ctx.cache) as cmd:
            for entry in self._ctx.args.to:
                if entry[0] == "data":
                    cmd.push_data_s3(entry[1], entry[2])
                elif entry[0] == "snapshot":
                    cmd.push_snapshot_s3(entry[1], entry[2])

        return 0

class CliEnumerateCache:
    """EnumerateCache command"""

    def __init__(self, ctx):
        self._ctx = ctx

    def run(self):
        """Run EnumerateCache command"""

        with enumerate_cache.EnumerateCache() as cmd:
            cmd.build()

        return 0

class Cli(contextlib.AbstractContextManager):
    """RPMrepo Command Line Interface"""

    EXITCODE_INVALID_COMMAND = 1

    def __init__(self, argv):
        self.args = None
        self.cache = None
        self.local = None
        self._argv = argv
        self._exitstack = None
        self._parser = None

    def _parse_args(self):
        self._parser = argparse.ArgumentParser(
            add_help=True,
            allow_abbrev=False,
            argument_default=None,
            description="RPM Repository Snapshot Management",
            prog="rpmrepo",
        )
        self._parser.add_argument(
            "--cache",
            help="Path to cache-directory to use",
            metavar="PATH",
            required=True,
            type=os.path.abspath,
        )
        self._parser.add_argument(
            "--local",
            help="Name to use for local indexing",
            metavar="NAME",
            type=str,
        )

        cmd = self._parser.add_subparsers(
            dest="cmd",
            title="RPMrepo Commands",
        )

        _cmd_index = cmd.add_parser(
            "index",
            add_help=True,
            allow_abbrev=False,
            argument_default=None,
            description="Create index for an RPM repository",
            help="Create RPM repository index",
            prog=f"{self._parser.prog} index",
        )

        cmd_pull = cmd.add_parser(
            "pull",
            add_help=True,
            allow_abbrev=False,
            argument_default=None,
            description="Pull an RPM repository to local storage",
            help="Fetch a full RPM Repository",
            prog=f"{self._parser.prog} pull",
        )
        cmd_pull.add_argument(
            "--base-url",
            help="RPM repository base URL to fetch from",
            metavar="URL",
            required=True,
            type=str,
        )
        cmd_pull.add_argument(
            "--platform-id",
            help="RPM platform ID to use",
            metavar="ID",
            required=True,
            type=str,
        )

        cmd_push = cmd.add_parser(
            "push",
            add_help=True,
            allow_abbrev=False,
            argument_default=None,
            description="Push an RPM repository to remote storage",
            help="Push a full RPM Repository",
            prog=f"{self._parser.prog} push",
        )
        cmd_push.add_argument(
            "--to",
            action="append",
            default=[],
            help="Target to push to",
            metavar="DESC",
            nargs=3,
            type=str,
        )

        cmd_push = cmd.add_parser(
            "enumerate-cache",
            add_help=True,
            allow_abbrev=False,
            argument_default=None,
            description="Build the cache for enumerate",
            help="Build the cache for enumerate",
            prog=f"{self._parser.prog} enumerate-cache",
        )

        return self._parser.parse_args(self._argv[1:])

    def _verify_args(self):
        if not self.args.cmd:
            print("No subcommand specified", file=sys.stderr)
            self._parser.print_help(file=sys.stderr)
            sys.exit(Cli.EXITCODE_INVALID_COMMAND)

    def __enter__(self):
        self._exitstack = contextlib.ExitStack()
        with self._exitstack:
            # Parse command-line arguments.
            self.args = self._parse_args()
            self._verify_args()

            # Create local identifier, if not specified.
            self.local = self.args.local
            if not self.local:
                self.local = uuid.uuid4().hex

            print("LocalIdentifier:", self.local, file=sys.stdout)

            # Create local cache directory, if non-existant.
            self.cache = os.path.join(self.args.cache, self.local)
            os.makedirs(self.cache, exist_ok=True)

            print("LocalCache:", self.cache, file=sys.stdout)

            # Setup succeeded, make sure to retain the exitstack for __exit__.
            self._exitstack = self._exitstack.pop_all()

        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self._exitstack.close()
        self._exitstack = None

    def run(self):
        """Execute selected commands"""

        if self.args.cmd == "index":
            ret = CliIndex(self).run()
        elif self.args.cmd == "pull":
            ret = CliPull(self).run()
        elif self.args.cmd == "push":
            ret = CliPush(self).run()
        elif self.args.cmd == "enumerate-cache":
            ret = CliEnumerateCache(self).run()
        else:
            raise RuntimeError("Command mismatch")

        return ret
