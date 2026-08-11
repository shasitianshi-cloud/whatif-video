#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MANIFEST="$ROOT/video-production/runtime/hyperframes-runtime-manifest.json"
VENDOR="$ROOT/vendor"
HF_RUNTIME="$VENDOR/hyperframes/runtime"
CHROME_VERSION="152.0.7928.2"
CHROME_ARCHIVE_SHA256="f0fa3d36fc961f17cb2c8b0b2c56c274b1834f1b7cdf3a8504af50706885d1b5"
CHROME_EXECUTABLE_SHA256="55efa0c5ec72d027235402198607cdb438c673297a287186d6f16a7ada8908d4"
HF_VERSION="0.7.106"

command -v node >/dev/null
command -v npm >/dev/null
command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null

NODE_OBSERVED="$(node --version)"
if [[ "$NODE_OBSERVED" != "v24.14.0" ]]; then
  echo "NODE_VERSION_MISMATCH expected=v24.14.0 observed=$NODE_OBSERVED" >&2
  exit 3
fi

mkdir -p "$VENDOR/chromium" "$HF_RUNTIME"
ARCHIVE="$VENDOR/chromium/chrome-headless-shell-linux64.zip"
CHROME_ROOT="$VENDOR/chromium/linux-$CHROME_VERSION"
BROWSER="$CHROME_ROOT/chrome-headless-shell-linux64/chrome-headless-shell"

if [[ ! -x "$BROWSER" ]]; then
  curl -fL --retry 2 --connect-timeout 15 --max-time 180 \
    "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-headless-shell-linux64.zip" \
    -o "$ARCHIVE"
  echo "$CHROME_ARCHIVE_SHA256  $ARCHIVE" | sha256sum -c -
  rm -rf "$CHROME_ROOT"
  unzip -q "$ARCHIVE" -d "$CHROME_ROOT"
fi

echo "$CHROME_EXECUTABLE_SHA256  $BROWSER" | sha256sum -c -

CLI="$HF_RUNTIME/node_modules/.bin/hyperframes"
if [[ ! -x "$CLI" ]]; then
  npm install --prefix "$HF_RUNTIME" --no-audit --no-fund "hyperframes@$HF_VERSION"
fi

HF_OBSERVED="$($CLI --version)"
if [[ "$HF_OBSERVED" != *"$HF_VERSION"* ]]; then
  echo "HYPERFRAMES_VERSION_MISMATCH expected=$HF_VERSION observed=$HF_OBSERVED" >&2
  exit 4
fi

export HYPERFRAMES_BROWSER_PATH="$BROWSER"
export HYPERFRAMES_NO_TELEMETRY=1
export HYPERFRAMES_NO_UPDATE_CHECK=1

printf '%s\n' "HYPERFRAMES_RUNTIME_MATERIALIZED=true"
printf '%s\n' "HYPERFRAMES_VERSION=$HF_VERSION"
printf '%s\n' "HYPERFRAMES_BROWSER_PATH=$BROWSER"
printf '%s\n' "HYPERFRAMES_RUNTIME_MANIFEST=$MANIFEST"
