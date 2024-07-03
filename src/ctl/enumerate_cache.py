"""rpmrepo - Create RPM Repository Enumerate Cache

This module enumerates all the thread indices to generate a list of
snapshots, which it then stores under data/thread/meta/cache.json.

"""

# pylint: disable=duplicate-code,invalid-name,too-few-public-methods

import contextlib
import json

import boto3

class EnumerateCache(contextlib.AbstractContextManager):
    """Create a cache of all the thread indices"""

    def __init__(self):
        pass

    def __exit__(self, exc_type, exc_value, exc_tb):
        pass

    def build(self):
        """Build the enumerate cache"""

        s3c = boto3.client("s3")

        results = []
        paginator = s3c.get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket="rpmrepo-storage",
            Prefix="data/thread/",
            PaginationConfig={'PageSize': 16384},
        )
        for page in pages:
            for entry in page.get("Contents", []):
                # get everything past the last slash
                key = entry.get("Key").rsplit("/", 1)[1]
                if len(key) > 0:
                    results.append(key)
        results.sort()

        s3c.put_object(
            Bucket="rpmrepo-storage",
            Key="data/thread/meta/cache.json",
            Body=json.dumps(results, indent="  ")
        )
