#!/usr/bin/env bash
set -euo pipefail

current_main=$(git ls-remote origin refs/heads/main | cut -f1)
if [ "$current_main" != "$REVISION" ]; then
  echo "A newer main commit exists; skipping latest and deployment."
  exit 0
fi
docker buildx imagetools create --tag "$IMAGE:latest" "$IMAGE:$REVISION"
echo "current=true" >> "$GITHUB_OUTPUT"
