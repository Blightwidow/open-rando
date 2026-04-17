#!/usr/bin/env bash
# Download go-pmtiles binary for Protomaps regional extract
set -euo pipefail

PMTILES_VERSION="1.30.1"
PMTILES_BIN="pmtiles"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== go-pmtiles Download ==="

if [ -x "./$PMTILES_BIN" ]; then
  echo "$PMTILES_BIN already exists, skipping"
  exit 0
fi

UNAME_S="$(uname -s)"
UNAME_M="$(uname -m)"

case "$UNAME_S" in
  Darwin) OS="Darwin" ;;
  Linux)  OS="Linux" ;;
  *) echo "ERROR: unsupported OS $UNAME_S"; exit 1 ;;
esac

case "$UNAME_M" in
  arm64|aarch64) ARCH="arm64" ;;
  x86_64)        ARCH="x86_64" ;;
  *) echo "ERROR: unsupported arch $UNAME_M"; exit 1 ;;
esac

ARCHIVE="go-pmtiles-${PMTILES_VERSION}_${OS}_${ARCH}.zip"
URL="https://github.com/protomaps/go-pmtiles/releases/download/v${PMTILES_VERSION}/${ARCHIVE}"

echo "Downloading ${URL}..."
curl -fL -o "$ARCHIVE" "$URL"
unzip -o "$ARCHIVE" "$PMTILES_BIN"
chmod +x "$PMTILES_BIN"
rm -f "$ARCHIVE"

echo "=== Download complete ==="
./"$PMTILES_BIN" version
echo "Run 'make -f Makefile.protomaps' to build france.pmtiles"
