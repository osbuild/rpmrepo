"""rpmrepo - Push RPM Repository

This module implements the functions that push local RPM repository
snapshots to configured remote storage.
"""

# pylint: disable=duplicate-code,invalid-name,too-few-public-methods

import contextlib
import os

import boto3


class Push(contextlib.AbstractContextManager):
    """Push RPM repository"""

    def __init__(self, cache):
        self._cache = cache
        self._path_conf = os.path.join(cache, "conf")
        self._path_data = os.path.join(cache, "index/data")
        self._path_snapshot = os.path.join(cache, "index/snapshot")

    def __exit__(self, exc_type, exc_value, exc_tb):
        pass

    def push_data_s3(self, storage, platform_id):
        """Push data to S3"""

        assert os.access(os.path.join(self._path_conf, "index.ok"), os.R_OK)
        assert storage in ["public", "rhvpn"]

        s3c = boto3.client("s3")

        n_total = 0
        for _, _, entries in os.walk(self._path_data):
            for entry in entries:
                n_total += 1

        i_total = 0
        for level, _, entries in os.walk(self._path_data):
            levelpath = os.path.relpath(level, self._path_data)
            if levelpath == ".":
                path = platform_id
            else:
                path = os.path.join(platform_id, levelpath)

            for entry in entries:
                i_total += 1

                print(f"[{i_total}/{n_total}] 'data/{storage}/{path}/{entry}'")

                with open(os.path.join(level, entry), "rb") as filp:
                    s3c.upload_fileobj(
                        filp,
                        "rpmrepo-storage",
                        f"data/{storage}/{path}/{entry}",
                    )

    def push_snapshot_s3(self, snapshot_id, snapshot_suffix):
        """Push snapshot to S3"""

        assert os.access(os.path.join(self._path_conf, "index.ok"), os.R_OK)

        s3c = boto3.client("s3")

        n_total = 0
        for _, _, entries in os.walk(self._path_snapshot):
            for entry in entries:
                n_total += 1

        i_total = 0
        for level, _subdirs, entries in os.walk(self._path_snapshot):
            levelpath = os.path.relpath(level, self._path_snapshot)
            if levelpath == ".":
                path = os.path.join(snapshot_id + snapshot_suffix)
            else:
                path = os.path.join(snapshot_id + snapshot_suffix, levelpath)

            for entry in entries:
                i_total += 1

                with open(os.path.join(level, entry), "rb") as filp:
                    checksum = filp.read().decode()

                print(f"[{i_total}/{n_total}] '{path}/{entry}' -> {checksum}")

                s3c.put_object(
                    Body=b"",
                    Bucket="rpmrepo-storage",
                    Key=f"data/ref/{path}/{entry}",
                    Metadata={"rpmrepo-checksum": checksum},
                )

        s3c.put_object(
            Body=b"",
            Bucket="rpmrepo-storage",
            Key=f"data/thread/{snapshot_id}/{snapshot_id}{snapshot_suffix}",
        )
