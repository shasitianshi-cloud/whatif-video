#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLI="$ROOT/vendor/hyperframes/runtime/node_modules/.bin/hyperframes"
BROWSER="$ROOT/vendor/chromium/linux-152.0.7928.2/chrome-headless-shell-linux64/chrome-headless-shell"

if [[ ! -x "$CLI" || ! -x "$BROWSER" ]]; then
  echo "HYPERFRAMES_RUNTIME_NOT_MATERIALIZED" >&2
  exit 3
fi

export HYPERFRAMES_BROWSER_PATH="$BROWSER"
export HYPERFRAMES_NO_TELEMETRY=1
export HYPERFRAMES_NO_UPDATE_CHECK=1

args=("$@")
if [[ ${#args[@]} -gt 0 && "${args[0]}" == "render" ]]; then
  has_json=false
  for arg in "${args[@]}"; do
    if [[ "$arg" == "--json" ]]; then
      has_json=true
      break
    fi
  done
  if [[ "$has_json" == false ]]; then
    args+=("--json")
  fi
fi

exec "$CLI" "${args[@]}"
