#!/usr/bin/env bash
# Build the card and copy it into a Home Assistant config's www/ folder.
# Usage: scripts/install-dev.sh [HA_CONFIG_DIR]
# Default target is the dev container's config. Never point this at production HAOS.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
config="${1:-/workspaces/home-assistant-core/config}"

if [[ ! -f "$config/configuration.yaml" ]]; then
  echo "error: $config does not look like a Home Assistant config directory" >&2
  exit 1
fi

node "$here/scripts/build.mjs"
version="$(node -p "require('$here/package.json').version")"
target="$config/www/rainbird-iq4"
fresh_www=0
[[ -d "$config/www" ]] || fresh_www=1
mkdir -p "$target"
cp "$here/dist/rainbird-iq4-card.js" "$target/rainbird-iq4-card.js"

echo "installed $target/rainbird-iq4-card.js"
echo "resource URL: /local/rainbird-iq4/rainbird-iq4-card.js?v=$version (type: JavaScript module)"
if [[ $fresh_www -eq 1 ]]; then
  echo "note: www/ was just created; restart Home Assistant once so it serves /local/."
fi
