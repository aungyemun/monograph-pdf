#!/usr/bin/env bash
# Development launch without a frozen .app.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
unset DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH
PY="$ROOT/env/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing ./env. Run bash scripts/setup_env.sh first." >&2
  exit 1
fi
# OCR wrapper sets its own DYLD to tools/ocr-env/lib; keep the app process clean.
exec "$PY" -m app "$@"
