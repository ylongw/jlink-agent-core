#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO_ROOT/skills/openclaw/jlink-debug"
DST_ROOT="${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/workspace/skills}"
DST="$DST_ROOT/jlink-debug"

if [ ! -d "$SRC" ]; then
  echo "Source skill not found: $SRC" >&2
  exit 1
fi

mkdir -p "$DST_ROOT"
rm -rf "$DST"
cp -R "$SRC" "$DST"

echo "Installed OpenClaw skill: $DST"
echo "You can now use the 'jlink-debug' skill in OpenClaw."
