#!/usr/bin/env bash
# Launch Monograph PDF from source on Linux.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Keep OCR-library overrides out of the macOS Python / Qt process.
if [[ "$(uname -s)" == "Darwin" ]]; then
  unset DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH
fi
PY="$ROOT/env/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing ./env. Run: bash scripts/setup_env.sh" >&2
  exit 1
fi
exec "$PY" -m app "$@"
