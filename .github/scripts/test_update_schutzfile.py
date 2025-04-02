#!/usr/bin/python3

"""update_schutzfile tests"""


import json
import os
import pytest

import update_schutzfile

# pylint: disable=missing-function-docstring

SCHUTZFILE_INPUT_TEST_DISTRO = {
    "test_distro": {
        "repos": [
            {
                "file": "bogus",
                "test_arch": [
                    {
                        "baseurl": "http://realurl.org/realrepo-12345678",
                    },
                    {
                        "baseurl": "http://realurl.org/realotherrepo-12345678",
                    },
                ],
            },
        ],
    },
}


SCHUTZFILE_INPUT = [
    # base case
    (
        SCHUTZFILE_INPUT_TEST_DISTRO,
        {
            "test_distro": {
                "repos": [
                    {
                        "file": "bogus",
                        "test_arch": [
                            {
                                "baseurl": "http://realurl.org/realrepo-87654321",
                            },
                            {
                                "baseurl": "http://realurl.org/realotherrepo-87654321",
                            },
                        ],
                    },
                ],
            },
        },
        [],
        [
            "realrepo-12345678",
            "realotherrepo-12345678",
            "realrepo-87654321",
            "realotherrepo-87654321",
        ],
    ),
    # no updates if one snapshot in arch is missing
    (
        SCHUTZFILE_INPUT_TEST_DISTRO,
        {
            "test_distro": {
                "repos": [
                    {
                        "file": "bogus",
                        "test_arch": [
                            {
                                "baseurl": "http://realurl.org/realrepo-12345678",
                            },
                            {
                                "baseurl": "http://realurl.org/realotherrepo-12345678",
                            },
                        ],
                    },
                ],
            },
        },
        [],
        [
            "realrepo-12345678",
            "realotherrepo-12345678",
            "realrepo-87654321",
        ],
    ),
    # old snapshots missing is fine
    (
        SCHUTZFILE_INPUT_TEST_DISTRO,
        {
            "test_distro": {
                "repos": [
                    {
                        "file": "bogus",
                        "test_arch": [
                            {
                                "baseurl": "http://realurl.org/realrepo-87654321",
                            },
                            {
                                "baseurl": "http://realurl.org/realotherrepo-87654321",
                            },
                        ],
                    },
                ],
            },
        },
        [],
        [
            "realrepo-12345678",
            "realrepo-87654321",
            "realotherrepo-87654321",
        ],
    ),
    # non-snapshot repos are ignored
    (
        {
            "test_distro": {
                "repos": [
                    {
                        "file": "bogus",
                        "test_arch": [
                            {
                                "baseurl": "http://realurl.org/realrepo-nosnapshot",
                            },
                            {
                                "baseurl": "http://realurl.org/realotherrepo-12345678",
                            },
                        ],
                    },
                ],
            },
        },
        {
            "test_distro": {
                "repos": [
                    {
                        "file": "bogus",
                        "test_arch": [
                            {
                                "baseurl": "http://realurl.org/realrepo-nosnapshot",
                            },
                            {
                                "baseurl": "http://realurl.org/realotherrepo-87654321",
                            },
                        ],
                    },
                ],
            },
        },
        [],
        [
            "realotherrepo-12345678",
            "realotherrepo-87654321",
        ],
    ),
    # no updates just for singletons
    (
        SCHUTZFILE_INPUT_TEST_DISTRO,
        {
            "test_distro": {
                "repos": [
                    {
                        "file": "bogus",
                        "test_arch": [
                            {
                                "baseurl": "http://realurl.org/realrepo-12345678",
                            },
                            {
                                "baseurl": "http://realurl.org/realotherrepo-87654321",
                            },
                        ],
                    },
                ],
            },
        },
        ["realrepo-12345678"],
        [
            "realrepo-12345678",
            "realotherrepo-12345678",
            "realrepo-87654321",
            "realotherrepo-87654321",
        ],
    ),
    # no updates in case of singleton and missing snapshots
    (
        {
            "test_distro": {
                "repos": [
                    {
                        "file": "bogus",
                        "test_arch": [
                            {
                                "baseurl": "http://realurl.org/realrepo-12345678",
                            },
                            {
                                "baseurl": "http://realurl.org/realotherrepo-12345678",
                            },
                            {
                                "baseurl": "http://realurl.org/realothersquaredrepo-12345678",
                            },
                        ],
                    },
                ],
            },
        },
        {
            "test_distro": {
                "repos": [
                    {
                        "file": "bogus",
                        "test_arch": [
                            {
                                "baseurl": "http://realurl.org/realrepo-12345678",
                            },
                            {
                                "baseurl": "http://realurl.org/realotherrepo-12345678",
                            },
                            {
                                "baseurl": "http://realurl.org/realothersquaredrepo-12345678",
                            },
                        ],
                    },
                ],
            },
        },
        ["realrepo-12345678"],
        [
            "realrepo-12345678",
            "realotherrepo-12345678",
            "realothersquaredrepo-12345678",
            "realotherrepo-87654321",
        ],
    ),
]


@pytest.mark.parametrize("input_sf,exp_sf,singletons,live_snapshots", SCHUTZFILE_INPUT)
def test_write_schutzfile(tmp_path, input_sf, exp_sf, singletons, live_snapshots):
    with open(os.path.join(tmp_path, "Schutzfile"), "w", encoding="utf-8") as filp:
        json.dump(input_sf, filp, indent=2)

    update_schutzfile.write_schutzfile(
        tmp_path, False, "87654321", singletons, live_snapshots
    )

    with open(os.path.join(tmp_path, "Schutzfile"), "r", encoding="utf-8") as filp:
        data = json.load(filp)
    assert exp_sf == data


REPOSITORIES_INPUT_ARCH = {
    "test_arch": [
        {
            "baseurl": "http://realurl.org/realrepo-12345678",
        },
        {
            "baseurl": "http://realurl.org/realotherrepo-12345678",
        },
    ],
}

REPOSITORIES_INPUT = [
    # base case
    (
        REPOSITORIES_INPUT_ARCH,
        {
            "test_arch": [
                {
                    "baseurl": "http://realurl.org/realrepo-87654321",
                },
                {
                    "baseurl": "http://realurl.org/realotherrepo-87654321",
                },
            ],
        },
        [],
        [
            "realrepo-12345678",
            "realotherrepo-12345678",
            "realrepo-87654321",
            "realotherrepo-87654321",
        ],
    ),
    # no updates for singletons
    (
        REPOSITORIES_INPUT_ARCH,
        {
            "test_arch": [
                {
                    "baseurl": "http://realurl.org/realrepo-12345678",
                },
                {
                    "baseurl": "http://realurl.org/realotherrepo-87654321",
                },
            ],
        },
        ["realrepo-12345678"],
        [
            "realrepo-12345678",
            "realotherrepo-12345678",
            "realotherrepo-87654321",
        ],
    ),
    # no updates if one snapshot in arch is missing
    (
        REPOSITORIES_INPUT_ARCH,
        {
            "test_arch": [
                {
                    "baseurl": "http://realurl.org/realrepo-12345678",
                },
                {
                    "baseurl": "http://realurl.org/realotherrepo-12345678",
                },
            ],
        },
        [],
        [
            "realrepo-12345678",
            "realotherrepo-12345678",
            "realotherrepo-87654321",
        ],
    ),
    # old snapshots missing is fine
    (
        REPOSITORIES_INPUT_ARCH,
        {
            "test_arch": [
                {
                    "baseurl": "http://realurl.org/realrepo-87654321",
                },
                {
                    "baseurl": "http://realurl.org/realotherrepo-87654321",
                },
            ],
        },
        [],
        [
            "realrepo-12345678",
            "realrepo-87654321",
            "realotherrepo-87654321",
        ],
    ),
    # non-snapshot repos are ignored
    (
        {
            "test_arch": [
                {
                    "baseurl": "http://realurl.org/realrepo-nosnapshot",
                },
                {
                    "baseurl": "http://realurl.org/realotherrepo-12345678",
                },
            ],
        },
        {
            "test_arch": [
                {
                    "baseurl": "http://realurl.org/realrepo-nosnapshot",
                },
                {
                    "baseurl": "http://realurl.org/realotherrepo-87654321",
                },
            ],
        },
        [],
        [
            "realotherrepo-12345678",
            "realotherrepo-87654321",
        ],
    ),
    # no updates in case of singleton and missing snapshots
    (
        {
            "test_arch": [
                {
                    "baseurl": "http://realurl.org/realrepo-12345678",
                },
                {
                    "baseurl": "http://realurl.org/realotherrepo-12345678",
                },
                {
                    "baseurl": "http://realurl.org/realothersquaredrepo-12345678",
                },
            ],
        },
        {
            "test_arch": [
                {
                    "baseurl": "http://realurl.org/realrepo-12345678",
                },
                {
                    "baseurl": "http://realurl.org/realotherrepo-12345678",
                },
                {
                    "baseurl": "http://realurl.org/realothersquaredrepo-12345678",
                },
            ],
        },
        ["realrepo-12345678"],
        [
            "realrepo-12345678",
            "realotherrepo-12345678",
            "realothersquaredrepo-12345678",
            "realotherrepo-87654321",
        ],
    ),
]


@pytest.mark.parametrize("input_r,exp_r,singletons,live_snapshots", REPOSITORIES_INPUT)
def test_write_test_repositories(tmp_path, input_r, exp_r, singletons, live_snapshots):
    os.makedirs(os.path.join(tmp_path, "test/data/repositories"))
    repo_path = os.path.join(tmp_path, "test/data/repositories", "repo.json")

    with open(repo_path, "w", encoding="utf-8") as filp:
        json.dump(input_r, filp, indent=2)

    update_schutzfile.write_test_repositories(
        tmp_path, False, "87654321", singletons, live_snapshots
    )

    with open(repo_path, "r", encoding="utf-8") as filp:
        data = json.load(filp)
    assert exp_r == data
