#!/usr/bin/env bash
# Create ./env and install locked requirements (Linux).
# Usage: bash scripts/setup_env.sh [--allow-other-python]
#
# Releases target Python 3.11 (same pin as Windows). Prefer python3.11, then
# uv-managed CPython 3.11. --allow-other-python accepts another 3.x for source-only work.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ALLOW_OTHER=0
for arg in "$@"; do
  case "$arg" in
    --allow-other-python) ALLOW_OTHER=1 ;;
  esac
done

pick_python() {
  local candidates=()
  local local_python
  for local_python in "$ROOT/tools/python/python/bin/python3.11" "$ROOT/tools/python/bin/python3.11"; do
    if [[ -x "$local_python" ]]; then
      candidates+=("$local_python")
    fi
  done
  if command -v python3.11 >/dev/null 2>&1; then
    candidates+=("python3.11")
  fi
  if [[ -x "$HOME/.local/bin/python3.11" ]]; then
    candidates+=("$HOME/.local/bin/python3.11")
  fi
  if command -v python3 >/dev/null 2>&1; then
    candidates+=("python3")
  fi
  local c ver
  for c in "${candidates[@]}"; do
    ver="$("$c" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
    if [[ "$ver" == "3.11" ]] || [[ "$ALLOW_OTHER" == "1" && "$ver" == 3.* ]]; then
      echo "$c"
      return 0
    fi
    echo "Skipping Python $ver at $c (Python 3.11 required; use --allow-other-python for source-only work)" >&2
  done
  return 1
}

PYTHON="$(pick_python)" || {
  echo "Python 3.11 not found. Install it (e.g. uv python install 3.11) and retry." >&2
  exit 1
}
echo "Using $PYTHON ($("$PYTHON" -c 'import sys; print(sys.version.split()[0])'))"

if [[ ! -x "$ROOT/env/bin/python" ]]; then
  "$PYTHON" -m venv "$ROOT/env"
fi
ENV_PY="$ROOT/env/bin/python"
ENV_VER="$("$ENV_PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if [[ "$ENV_VER" != "3.11" && "$ALLOW_OTHER" != "1" ]]; then
  echo "The existing ./env uses Python $ENV_VER, not 3.11. Delete env/ and run again." >&2
  exit 1
fi

"$ENV_PY" -m pip install --upgrade pip || echo "Could not upgrade pip (no network?); continuing." >&2
mkdir -p "$ROOT/packages/wheels"
WHEEL_COUNT="$(find "$ROOT/packages/wheels" -maxdepth 1 -name '*.whl' 2>/dev/null | wc -l | tr -d ' ')"
if [[ "${WHEEL_COUNT:-0}" -gt 0 ]]; then
  echo "Installing from $WHEEL_COUNT cached wheel(s) in packages/wheels"
  "$ENV_PY" -m pip install --no-index --find-links "$ROOT/packages/wheels" --cache-dir "$ROOT/packages/wheels" -r "$ROOT/requirements.txt"
else
  "$ENV_PY" -m pip install --cache-dir "$ROOT/packages/wheels" -r "$ROOT/requirements.txt"
fi
if [[ -f "$ROOT/requirements-ci.txt" ]]; then
  echo "Installing requirements-ci.txt (test/signing tooling)"
  if [[ "${WHEEL_COUNT:-0}" -gt 0 ]]; then
    "$ENV_PY" -m pip install --no-index --find-links "$ROOT/packages/wheels" --cache-dir "$ROOT/packages/wheels" -r "$ROOT/requirements-ci.txt" || true
  else
    "$ENV_PY" -m pip install --cache-dir "$ROOT/packages/wheels" -r "$ROOT/requirements-ci.txt" || true
  fi
fi
"$ENV_PY" -m pip check
"$ENV_PY" -m pip download -r "$ROOT/requirements.txt" -d "$ROOT/packages/wheels" --cache-dir "$ROOT/packages/wheels" || \
  echo "Wheel cache download failed (offline?); env itself is complete." >&2
echo "Environment ready: $ENV_PY"
