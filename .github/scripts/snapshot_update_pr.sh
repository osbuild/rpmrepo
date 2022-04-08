#!/bin/bash

# This script is meant to be run as a part of a workflow 
# which sets the necessary environment variables

# run a helper script that updates Schutzfile with new snapshots
python3 .github/scripts/update_schutzfile.py --repo "$REPO" --suffix "$SUFFIX"

# Open PR with updated Schutzfile
pushd "$REPO"
git diff
git config --unset-all http.https://github.com/.extraheader
git config user.name "schutzbot"
git config user.email "schutzbot@gmail.com"
git checkout -b snapshots-"$SUFFIX"
git add Schutzfile
git commit -m "schutzfile: Update snapshots to ${SUFFIX}"
git push https://"$GITHUB_TOKEN"@github.com/schutzbot/"$REPO".git

cat <<EOF > "body"
Job(s) succeeded: $JOBS_SUCCEEDED
Job(s) failed: $JOBS_FAILED
Workflow run: https://github.com/osbuild/rpmrepo/actions/runs/$WORKFLOW_RUN
EOF

gh pr create \
  -t "Update snapshots to $SUFFIX" \
  -F "body" \
  --repo "osbuild/$REPO" \
  --base "main" \
  --head "schutzbot:snapshots-$SUFFIX"
popd
