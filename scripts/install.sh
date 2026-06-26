#!/usr/bin/env bash
# Install window_advisor into a Home Assistant config directory.
#
# Layout after install:
#   $HA_CONFIG/.window_advisor_repo/        ← full git clone (source of truth)
#   $HA_CONFIG/custom_components/window_advisor → symlink into the clone
#
# Usage:
#   scripts/install.sh /path/to/ha/config
#   scripts/install.sh                    # defaults to /config (HAOS)
#
# Re-running is safe: skips clone if already present, re-points symlink.

set -euo pipefail

REPO_URL="${REPO_URL:-http://truenas.lan:30142/dionm11/window-advisor.git}"
BRANCH="${BRANCH:-main}"
HA_CONFIG="${1:-/config}"

if [[ ! -d "$HA_CONFIG" ]]; then
  echo "error: HA config dir not found: $HA_CONFIG" >&2
  echo "usage: $0 <ha_config_dir>" >&2
  exit 1
fi

CLONE_DIR="$HA_CONFIG/.window_advisor_repo"
CC_DIR="$HA_CONFIG/custom_components"
TARGET="$CC_DIR/window_advisor"

mkdir -p "$CC_DIR"

if [[ -d "$CLONE_DIR/.git" ]]; then
  echo "→ existing clone at $CLONE_DIR — fetching latest"
  git -C "$CLONE_DIR" fetch --quiet origin
  git -C "$CLONE_DIR" checkout --quiet "$BRANCH"
  git -C "$CLONE_DIR" pull --ff-only --quiet
else
  echo "→ cloning $REPO_URL → $CLONE_DIR"
  git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$CLONE_DIR"
fi

SRC="$CLONE_DIR/custom_components/window_advisor"
if [[ ! -d "$SRC" ]]; then
  echo "error: repo missing custom_components/window_advisor at $SRC" >&2
  exit 1
fi

if [[ -L "$TARGET" || -e "$TARGET" ]]; then
  rm -rf "$TARGET"
fi
ln -s "$SRC" "$TARGET"
echo "→ linked $TARGET → $SRC"

echo
echo "✓ Installed window_advisor."
echo "  Add the sensor + binary_sensor config from config.example.yaml"
echo "  to your configuration.yaml, then restart Home Assistant."
