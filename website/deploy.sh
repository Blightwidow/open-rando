#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Build site (prebuild copies data from ~/.local/share/open-rando/data/)
bun run build

# Deploy dist/ to gh-pages branch
cd dist
echo "rando.dammaretz.fr" > CNAME

REMOTE_URL="$(git -C "$SCRIPT_DIR" remote get-url origin)"

git init
git checkout -b gh-pages
git add -A
git commit -m "deploy $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
git push -f "$REMOTE_URL" gh-pages:gh-pages

echo "Deployed to https://rando.dammaretz.fr"
