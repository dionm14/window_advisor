#!/usr/bin/env bash
# Pull latest window_advisor changes. Restart Home Assistant after.
#
# Usage:
#   scripts/update.sh /path/to/ha/config
#   scripts/update.sh                    # defaults to /config

set -euo pipefail

HA_CONFIG="${1:-/config}"
BRANCH="${BRANCH:-main}"
CLONE_DIR="$HA_CONFIG/.window_advisor_repo"

if [[ ! -d "$CLONE_DIR/.git" ]]; then
  echo "error: no clone at $CLONE_DIR — run install.sh first" >&2
  exit 1
fi

OLD="$(git -C "$CLONE_DIR" rev-parse HEAD)"
git -C "$CLONE_DIR" fetch --quiet origin
git -C "$CLONE_DIR" checkout --quiet "$BRANCH"
git -C "$CLONE_DIR" pull --ff-only
NEW="$(git -C "$CLONE_DIR" rev-parse HEAD)"

if [[ "$OLD" == "$NEW" ]]; then
  echo "✓ Already up to date ($OLD)."
else
  echo "✓ Updated: $OLD → $NEW"
  echo "  Restart Home Assistant to load changes."
fi
