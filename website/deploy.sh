#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Publish only reviewed code: a clean checkout of main that matches origin/main.
# ALLOW_UNREVIEWED_DEPLOY=1 skips the check on purpose (hotfix, preview of a branch).
if [ "${ALLOW_UNREVIEWED_DEPLOY:-}" != "1" ]; then
  current_branch="$(git rev-parse --abbrev-ref HEAD)"
  if [ "$current_branch" != "main" ]; then
    echo "Refusing to deploy from '$current_branch': switch to main (or set ALLOW_UNREVIEWED_DEPLOY=1)." >&2
    exit 1
  fi
  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "Refusing to deploy with uncommitted changes to tracked files." >&2
    exit 1
  fi
  git fetch --quiet origin main
  if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
    echo "Refusing to deploy: local main differs from origin/main (pull or push first)." >&2
    exit 1
  fi
fi
DEPLOYED_COMMIT="$(git rev-parse --short HEAD)"

# Build site (prebuild copies data from ~/.local/share/open-rando/data/)
bun run build

# Refuse a build whose data lacks the mobile manifests (grid.json, routes/<id>/pmtiles.json):
# they are not written by the data pipeline, and missing ones only show up as 404s in production.
if [ "${ALLOW_MISSING_TILE_MANIFESTS:-}" != "1" ]; then
  bun scripts/check-tile-manifests.mjs dist/data
fi

# Deploy dist/ to gh-pages branch
cd dist
echo "rando.dammaretz.fr" > CNAME

REMOTE_URL="$(git -C "$SCRIPT_DIR" remote get-url origin)"

git init
git checkout -b gh-pages
git add -A
git commit -m "deploy $DEPLOYED_COMMIT $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
git push -f "$REMOTE_URL" gh-pages:gh-pages

echo "Deployed to https://rando.dammaretz.fr"
