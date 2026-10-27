#!/bin/bash

# This script is meant to be run as a part of a workflow
# which sets the necessary environment variables

# get latest snapshot date, but caller can override it by providing it
if [ -z "${SUFFIX:-}" ]; then
    SUFFIX=$(
        set -o pipefail
        curl --fail --silent --show-error https://rpmrepo.osbuild.org/v2/enumerate |
            jq -er '[.[] | capture("-(?<date>[0-9]{8})$").date] | max // empty'
    ) || exit 1
fi

EXISTING_PR=$(gh pr list \
    --repo "osbuild/$REPO" \
    --base main \
    --head "schutzbot:snapshots-$SUFFIX" \
    --state open \
    --json number --jq 'length') || exit 1
if [ "$EXISTING_PR" -gt 0 ]; then
    echo "A snapshot update PR already exists for $SUFFIX; skipping."
    exit 0
fi

# run a helper script that updates Schutzfile with new snapshots
UPDATE_SCHUTZFILE_OUTPUT=$(mktemp)
python3 .github/scripts/update_schutzfile.py --repo "$REPO" --suffix "$SUFFIX" > "$UPDATE_SCHUTZFILE_OUTPUT" 2>&1

pushd "$REPO" || exit 2

if [ -e ./tools/check-snapshots ]; then
    echo "Checking snapshots..."
    CHECK_SNAPSHOT_SUCCEEDED=false
    if ./tools/check-snapshots --errors-only .; then
        CHECK_SNAPSHOT_SUCCEEDED=true
    fi
fi

# Update manifest checksums in osbuild/image-builder.
# Identify by checking for the script.
if [ -e ./tools/gen-manifest-checksums.sh ]; then
    echo "Updating manifest checksums"
    ./tools/gen-manifest-checksums.sh
fi

# Open PR with updated Schutzfile
git add Schutzfile
if [ -d "test/data/repositories/" ]; then
    git add test/data/repositories/
fi
if [ -d "test/data/manifest-checksums/" ]; then
    git add test/data/manifest-checksums/
fi
if git diff --cached --quiet; then
    echo "No snapshot changes available for $SUFFIX; skipping."
    popd || exit 2
    exit 0
elif [ "$?" -ne 1 ]; then
    exit 1
fi

git diff --cached
git config --unset-all http.https://github.com/.extraheader
git config user.name "schutzbot"
git config user.email "schutzbot@gmail.com"
git checkout -b snapshots-"$SUFFIX"
git commit -m "schutzfile: Update snapshots to ${SUFFIX}"
git push https://"$GITHUB_TOKEN"@github.com/schutzbot/"$REPO".git

cat <<EOF > "body"
Snapshot:
${SUFFIX}

Check snapshots exist in rpmrepo: $CHECK_SNAPSHOT_SUCCEEDED

Triggered by workflow: ${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}

---

<details>
<summary>update_schutzfile.py output</summary>

$(cat "$UPDATE_SCHUTZFILE_OUTPUT")

</details>

EOF

gh pr create \
  -t "Update snapshots to $SUFFIX" \
  -F "body" \
  --repo "osbuild/$REPO" \
  --base "main" \
  --head "schutzbot:snapshots-$SUFFIX"
popd || exit 2
