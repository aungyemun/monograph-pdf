#!/usr/bin/env bash
# Create ./env and install locked requirements (macOS).
# Usage: bash scripts/setup_env.sh [--allow-other-python]
#
# Prefers a project-local Python 3.11 under tools/python, then python3.11 on PATH.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ALLOW_OTHER=0
if [[ "${1:-}" == "--allow-other-python" ]]; then
  ALLOW_OTHER=1
fi

pick_python() {
  local candidates=(
    "$ROOT/tools/python/python/bin/python3.11"
    "$ROOT/tools/python/bin/python3.11"
    "python3.11"
    "python3"
  )
  local c ver
  for c in "${candidates[@]}"; do
    if ! command -v "$c" >/dev/null 2>&1 && [[ ! -x "$c" ]]; then
      continue
    fi
    ver="$("$c" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
    if [[ "$ver" == "3.11" ]] || [[ "$ALLOW_OTHER" == "1" && "$ver" == 3.* ]]; then
      echo "$c"
      return 0
    fi
    echo "Skipping Python $ver at $c (need 3.11; use --allow-other-python for source-only work)" >&2
  done
  return 1
}

PYTHON="$(pick_python)" || {
  echo "Python 3.11 not found. Place a build under tools/python or install python@3.11." >&2
  exit 1
}
echo "Using $PYTHON"
if [[ ! -x "$ROOT/env/bin/python" ]]; then
  "$PYTHON" -m venv "$ROOT/env"
fi
ENV_PY="$ROOT/env/bin/python"
ver="$("$ENV_PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if [[ "$ver" != "3.11" && "$ALLOW_OTHER" != "1" ]]; then
  echo "Existing ./env uses Python $ver, not 3.11. Delete env/ and re-run." >&2
  exit 1
fi
"$ENV_PY" -m pip install --upgrade pip || echo "pip upgrade skipped (no network?)" >&2
mkdir -p "$ROOT/packages/wheels"
if compgen -G "$ROOT/packages/wheels/*.whl" >/dev/null; then
  echo "Installing from cached wheels in packages/wheels"
  "$ENV_PY" -m pip install --no-index --find-links "$ROOT/packages/wheels" -r "$ROOT/requirements.txt"
else
  "$ENV_PY" -m pip install --cache-dir "$ROOT/packages/wheels" -r "$ROOT/requirements.txt"
fi
if [[ -f "$ROOT/requirements-ci.txt" ]]; then
  "$ENV_PY" -m pip install --cache-dir "$ROOT/packages/wheels" -r "$ROOT/requirements-ci.txt" || \
    echo "requirements-ci.txt install failed; core env is still usable." >&2
fi
"$ENV_PY" -m pip check
"$ENV_PY" -m pip freeze > "$ROOT/packages/pip-freeze.txt" || true
# OCR notice next to the engine when present
if [[ -f "$ROOT/third_party/licenses/TESSERACT_NOTICE.txt" ]]; then
  mkdir -p "$ROOT/engines/ocr"
  cp "$ROOT/third_party/licenses/TESSERACT_NOTICE.txt" "$ROOT/engines/ocr/TESSERACT_NOTICE.txt"
fi
echo "Environment ready: $ROOT/env"
