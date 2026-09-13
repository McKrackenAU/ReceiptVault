#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-1.5.0}"
DEST="$ROOT/release"
mkdir -p "$DEST"
ARCHIVE="$DEST/receiptvault-${VERSION}.tar.gz"
tar --exclude='.git' --exclude='node_modules' --exclude='.venv' --exclude='backend/.venv' \
    --exclude='var' --exclude='release' --exclude='frontend/dist' \
    -C "$ROOT" -czf "$ARCHIVE" .
( cd "$DEST" && sha256sum "$(basename "$ARCHIVE")" > "$(basename "$ARCHIVE").sha256" )
echo "Wrote $ARCHIVE"
cat "$ARCHIVE.sha256"
