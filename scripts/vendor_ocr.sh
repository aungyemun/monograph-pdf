#!/usr/bin/env bash
# Stage OCR for Linux: system (or vendored) tesseract + pinned tessdata_fast eng/jpn/osd.
# Usage: bash scripts/vendor_ocr.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/env/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3.11 || command -v python3)"
fi
exec "$PY" "$ROOT/scripts/ci/stage_ocr_engine_linux.py" --require
