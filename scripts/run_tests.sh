#!/usr/bin/env bash
# Run unit, integration and UI tests; artifacts under tests/outputs only.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/env/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing ./env. Run: bash scripts/setup_env.sh" >&2
  exit 1
fi
JUNIT="$ROOT/tests/outputs/junit/pytest.xml"
LOG_DIR="$ROOT/tests/outputs/logs"
mkdir -p "$(dirname "$JUNIT")" "$LOG_DIR"
LOG="$LOG_DIR/pytest-$(date +%Y%m%d-%H%M%S).log"
# Offscreen Qt for headless CI / servers without a display
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
export MONOGRAPH_PDF_HEADLESS="${MONOGRAPH_PDF_HEADLESS:-1}"
set +e
"$PY" -m pytest tests/unit tests/integration tests/ui -q --junitxml="$JUNIT" 2>&1 | tee "$LOG"
code=${PIPESTATUS[0]}
set -e
exit "$code"
