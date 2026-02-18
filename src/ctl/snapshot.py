"""rpmrepo - Snapshot RPM Repository

This module implements the snapshot pipeline that pulls an RPM repository,
indexes it, and pushes it to remote storage.
"""

# pylint: disable=duplicate-code,invalid-name,too-few-public-methods

import datetime
import json
import os

import boto3
import botocore.exceptions

from . import index, pull, push


class Snapshot:
    """Snapshot RPM repository"""

    def __init__(self, cache_root):
        self._cache_root = cache_root

    @staticmethod
    def _load_config(path):
        with open(path, "r", encoding="utf-8") as filp:
            return json.load(filp)

    @staticmethod
    def _snapshot_suffix(conf):
        if singleton := conf.get("singleton"):
            return f"-{singleton}"
        return f"-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')}"

    @staticmethod
    def _snapshot_exists(snapshot_id, suffix):
        """Check whether a snapshot thread marker already exists in S3"""

        s3c = boto3.client("s3")
        key = f"data/thread/{snapshot_id}/{snapshot_id}{suffix}"
        try:
            s3c.head_object(Bucket="rpmrepo-storage", Key=key)
            return True
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    def run_one(self, path):
        """Run snapshot for a single repo config file"""

        conf = self._load_config(path)
        suffix = self._snapshot_suffix(conf)

        platform_id = conf["platform-id"]
        base_url = conf["base-url"]
        snapshot_id = conf["snapshot-id"]
        storage = conf["storage"]

        if self._snapshot_exists(snapshot_id, suffix):
            print(f"Snapshot {snapshot_id}{suffix} exists already, skipping")
            return

        # Derive a stable cache identifier from the snapshot-id so the
        # dnf cache is reused across runs of the same repo config.
        cache = os.path.join(self._cache_root, snapshot_id)
        os.makedirs(cache, exist_ok=True)
        print("LocalIdentifier:", snapshot_id)
        print("LocalCache:", cache)

        print(f"Pulling {snapshot_id} from {base_url}...")
        with pull.Pull(cache, platform_id, base_url) as cmd:
            cmd.pull()

        print(f"Indexing {snapshot_id}...")
        with index.Index(cache) as cmd:
            cmd.index()

        print(f"Pushing {snapshot_id}{suffix}...")
        with push.Push(cache) as cmd:
            cmd.push_data_s3(storage, platform_id)
            cmd.push_snapshot_s3(snapshot_id, suffix)

        print(f"Snapshot {snapshot_id}{suffix} complete.")
