"""rpmrepo - Snapshot RPM Repository

This module implements the snapshot pipeline that pulls an RPM repository,
indexes it, and pushes it to remote storage.
"""

# pylint: disable=duplicate-code,invalid-name,too-few-public-methods

import concurrent.futures
import datetime
import hashlib
import json
import os
import urllib.request

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

    @staticmethod
    def _fetch_repomd_checksum(base_url):
        """Fetch upstream repomd.xml and return its checksum.

        Returns None if the fetch fails, causing the caller to fall
        through to the full pipeline.
        """
        repomd_url = base_url.rstrip("/") + "/repodata/repomd.xml"
        try:
            with urllib.request.urlopen(repomd_url, timeout=30) as resp:
                data = resp.read()
            return "sha256-" + hashlib.sha256(data).hexdigest()
        except (OSError, ValueError) as err:
            print(f"Warning: failed to fetch repomd.xml from {repomd_url}: {err}")
            return None

    @staticmethod
    def _get_previous_repomd_checksum(snapshot_id, suffix):
        """Get the repomd.xml checksum from an existing snapshot's refs."""
        s3c = boto3.client("s3")
        key = f"data/ref/{snapshot_id}{suffix}/repodata/repomd.xml"
        try:
            resp = s3c.head_object(Bucket="rpmrepo-storage", Key=key)
            return resp["Metadata"].get("rpmrepo-checksum")
        except botocore.exceptions.ClientError:
            return None

    @staticmethod
    def _get_latest_suffix(snapshot_id):
        """Find the most recent snapshot suffix from S3 thread markers."""
        s3c = boto3.client("s3")
        prefix = f"data/thread/{snapshot_id}/{snapshot_id}-"

        suffixes = []
        paginator = s3c.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket="rpmrepo-storage", Prefix=prefix):
            for obj in page.get("Contents", []):
                name = obj["Key"].rsplit("/", 1)[-1]
                suffixes.append(name[len(snapshot_id):])

        if not suffixes:
            return None
        suffixes.sort()
        return suffixes[-1]

    @staticmethod
    def _clone_snapshot(snapshot_id, old_suffix, new_suffix):
        """Clone snapshot references from a previous suffix to a new one.

        Copies all ref objects and creates a new thread marker. Data objects
        are content-addressed and shared across snapshots, so they don't
        need copying.
        """
        s3c = boto3.client("s3")

        old_prefix = f"data/ref/{snapshot_id}{old_suffix}/"
        new_prefix = f"data/ref/{snapshot_id}{new_suffix}/"

        objects = []
        paginator = s3c.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket="rpmrepo-storage", Prefix=old_prefix):
            objects.extend(page.get("Contents", []))

        def copy_one(obj):
            old_key = obj["Key"]
            new_key = new_prefix + old_key[len(old_prefix):]
            s3c.copy_object(
                Bucket="rpmrepo-storage",
                CopySource={"Bucket": "rpmrepo-storage", "Key": old_key},
                Key=new_key,
                MetadataDirective="COPY",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
            list(executor.map(copy_one, objects))

        s3c.put_object(
            Body=b"",
            Bucket="rpmrepo-storage",
            Key=f"data/thread/{snapshot_id}/{snapshot_id}{new_suffix}",
        )

        return len(objects)

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

        # Check if the upstream repo has changed since the last snapshot.
        # If not, clone the previous snapshot's refs instead of re-pulling.
        upstream_checksum = self._fetch_repomd_checksum(base_url)
        if upstream_checksum is not None:
            prev_suffix = self._get_latest_suffix(snapshot_id)
            if prev_suffix is not None:
                prev_checksum = self._get_previous_repomd_checksum(
                    snapshot_id, prev_suffix,
                )
                if upstream_checksum == prev_checksum:
                    print(f"Upstream unchanged for {snapshot_id}, "
                          f"cloning {snapshot_id}{prev_suffix}...")
                    n = self._clone_snapshot(snapshot_id, prev_suffix, suffix)
                    print(f"Snapshot {snapshot_id}{suffix} cloned ({n} refs).")
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
