#!/usr/bin/env bash
set -euo pipefail

git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git remote add upstream https://github.com/glanceapp/glance.git
git fetch upstream main
if git merge-base --is-ancestor upstream/main HEAD; then
  echo "Already up to date."
  exit 0
fi

# Stop before committing, even for a possible fast-forward.
# Restore the entire directory, including additions/deletions,
# before checking for genuine conflicts outside workflow files.
merge_status=0
git merge --no-commit --no-ff upstream/main || merge_status=$?
git restore --source=HEAD --staged --worktree -- .github/workflows
conflicts=$(git diff --name-only --diff-filter=U)
if [ -n "$conflicts" ]; then
  {
    echo '### Upstream sync blocked by merge conflicts'
    echo '```'
    printf '%s\n' "$conflicts"
    echo '```'
    echo 'Merge upstream/main manually. No changes were pushed or deployed.'
  } >> "$GITHUB_STEP_SUMMARY"
  git merge --abort
  echo "conflict=true" >> "$GITHUB_OUTPUT"
  exit 0
fi
# A non-conflict Git failure must not be mistaken for success.
if ! git rev-parse --verify MERGE_HEAD >/dev/null; then
  echo "Merge failed with status $merge_status without a merge to commit." >&2
  exit 1
fi
git commit --no-edit
git diff --exit-code origin/main HEAD -- .github/workflows
