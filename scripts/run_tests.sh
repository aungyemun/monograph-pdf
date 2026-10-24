#!/usr/bin/env bash
# Run unit / integration / UI tests; artifacts under tests/outputs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Never inherit conda OCR libs into the Python process — they break OpenCV (cv2/iconv).
# The engines/ocr/tesseract wrapper sets DYLD only for the Tesseract subprocess.
unset DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH
PY="$ROOT/env/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing ./env. Run bash scripts/setup_env.sh first." >&2
  exit 1
fi
JUNIT="$ROOT/tests/outputs/junit/pytest.xml"
LOGDIR="$ROOT/tests/outputs/logs"
mkdir -p "$(dirname "$JUNIT")" "$LOGDIR"
LOG="$LOGDIR/pytest-$(date +%Y%m%d-%H%M%S).log"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
set +e
"$PY" -m pytest tests/unit tests/integration tests/ui -q --junitxml="$JUNIT" 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
exit "$rc"
