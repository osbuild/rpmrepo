#!/usr/bin/python3
"""repo-check - Check JSON repository files

A simple script to check the validity of repository configuration files that
we store in ./repo/.
"""

# pylint: disable=duplicate-code,invalid-name,too-few-public-methods

import argparse
import json
import os
import re
import urllib.parse

import requests


def _parse_args():
    parser = argparse.ArgumentParser(
        add_help=True,
        allow_abbrev=False,
        argument_default=None,
        description="JSON Repository File Verification",
        prog="repo-check.py",
    )
    parser.add_argument(
        "--check-external",
        action="append",
        help="Verify external references for the given storage type",
        metavar="STORAGE",
    )
    parser.add_argument(
        "FILES",
        help="List of files to check",
        nargs="*",
        type=os.path.abspath,
    )
    parser.set_defaults(check_external=[])

    return parser.parse_args()


class Repo:
    """Repository Configuration"""

    def __init__(self, data):
        self._data = data

    @classmethod
    def from_path(cls, path):
        """Load repository configuration from a file"""

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls(data)

    def dump(self):
        """Dump the configuration to standard output"""

        print(json.dumps(self._data, indent=4, sort_keys=True))

    def storage(self):
        """Query the storage identifier"""

        return self._data["storage"]

    def _verify_base_url(self):
        # mandatory
        assert "base-url" in self._data
        assert self._data["base-url"]

        # must be a valid URL
        url = urllib.parse.urlparse(self._data["base-url"])
        assert url is not None

        # We expect trailing slashes in the URL, as they denote directories
        # and we want path operations to work without hard-coding this.
        assert url.path and url.path[-1] == "/"

    def _verify_platform_id(self):
        # mandatory
        assert "platform-id" in self._data
        assert self._data["platform-id"]

        # must be a proper identifier
        assert re.match(r'^[A-Za-z0-9_-]+$', self._data["platform-id"])

    def _verify_singleton(self):
        # optional
        if "singleton" not in self._data:
            return

        assert self._data["singleton"]

        # must be a proper identifier
        assert re.match(r'^[A-Za-z0-9_-]+$', self._data["platform-id"])

    def _verify_snapshot_id(self):
        # mandatory
        assert "snapshot-id" in self._data
        assert self._data["snapshot-id"]

        # must be a proper identifier
        assert re.match(r'^[A-Za-z0-9_-]+$', self._data["platform-id"])

    def _verify_storage(self):
        # mandatory
        assert "storage" in self._data
        assert self._data["storage"]

        # must be a valid storage location
        assert self._data["storage"] in ["public", "rhvpn"]

    def verify_integrity(self):
        """Verify integrity of the repository configuration"""

        assert isinstance(self._data, dict)

        for e in self._data:
            assert isinstance(e, str)
            assert e in ["base-url", "platform-id", "singleton", "snapshot-id", "storage"]

        self._verify_base_url()
        self._verify_platform_id()
        self._verify_singleton()
        self._verify_snapshot_id()
        self._verify_storage()

    def _verify_base_url_reference(self):
        url = urllib.parse.urlparse(self._data["base-url"])
        url = url._replace(path=urllib.parse.urljoin(url.path, "repodata/repomd.xml"))

        h = requests.head(urllib.parse.urlunparse(url))
        if h.status_code != 200:
            raise ValueError(f"Cannot fetch repomd.xml: {urllib.parse.urlunparse(url)} {h}")

    def verify_references(self):
        """Verify references to external resources"""

        self._verify_base_url_reference()


def main():
    """Script Entrypoint"""

    args = _parse_args()

    print("------------------------")
    for f in args.FILES:
        print("Loading file:", f)
        r = Repo.from_path(f)

        print("Contents:")
        r.dump()

        r.verify_integrity()

        if r.storage in args.check_external:
            r.verify_references()

        print("------------------------")


if __name__ == "__main__":
    main()
