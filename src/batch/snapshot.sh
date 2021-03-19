#!/bin/bash

#
# Snapshot Creation
#
# This tool is run on AWS Batch and creates a new RPM repository snapshot.
#
# Parameters:
#
#     RPMREPO_BASEURL:
#     RPMREPO_PLATFORM_ID:
#     RPMREPO_SNAPSHOT_ID:
#     RPMREPO_SNAPSHOT_SUFFIX:
#     RPMREPO_STORAGE:
#

set -eox pipefail

cd "/osb"

mkdir -p "/var/lib/rpmrepo/cache"

python3 -m "rpmrepo.src.ctl" \
        --cache "/var/lib/rpmrepo/cache" \
        --local "batch" \
        pull \
                --base-url "${RPMREPO_BASEURL}" \
                --platform-id "${RPMREPO_PLATFORM_ID}"

python3 -m "rpmrepo.src.ctl" \
        --cache "/var/lib/rpmrepo/cache" \
        --local "batch" \
        index

python3 -m "rpmrepo.src.ctl" \
        --cache "/var/lib/rpmrepo/cache" \
        --local "batch" \
        push \
                --to \
                        "snapshot" \
                        "${RPMREPO_SNAPSHOT_ID}" \
                        "${RPMREPO_SNAPSHOT_SUFFIX}" \
                --to \
                        "data" \
                        "${RPMREPO_STORAGE}" \
                        "${RPMREPO_PLATFORM_ID}"

rm -rf "/var/lib/rpmrepo/cache"
