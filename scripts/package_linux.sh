#!/usr/bin/env bash
# Package dist/MonographPDF (from scripts/build_linux.sh) into the Linux release set:
#   MonographPDF_X.Y.Z_Linux_x86_64.tar.gz   built application + install.sh
#   MonographPDF_X.Y.Z_Linux_Source.tar.gz   committed source (git archive of HEAD)
#   SHA256SUMS.txt
# With --sign KEYID, also writes ASCII-armoured detached GPG signatures (*.asc) for every file
# above, including SHA256SUMS.txt. gpg asks for the key passphrase itself (pinentry).
#
# Usage: bash scripts/package_linux.sh [--sign KEYID] [OUT_DIR]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/env/bin/python"
SIGN_KEY=""
OUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sign) SIGN_KEY="${2:?--sign needs a key id}"; shift 2 ;;
    *) OUT="$1"; shift ;;
  esac
done
OUT="${OUT:-$ROOT/dist/release-linux}"
VERSION="$("$PY" scripts/read_version.py --platform linux | tr -d '[:space:]')"
DIST="$ROOT/dist/MonographPDF"

if [[ ! -x "$DIST/MonographPDF" ]]; then
  echo "Missing $DIST — run bash scripts/build_linux.sh first." >&2
  exit 1
fi
BUILT="$(tr -d '[:space:]' < "$DIST/VERSION")"
if [[ "$BUILT" != "$VERSION" ]]; then
  echo "ERROR: dist is version $BUILT, versions/linux.txt is $VERSION. Rebuild." >&2
  exit 1
fi
# The source archive is made from committed files only.
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "ERROR: uncommitted changes to tracked files; commit before packaging." >&2
  exit 1
fi

APP_TGZ="MonographPDF_${VERSION}_Linux_x86_64.tar.gz"
SRC_TGZ="MonographPDF_${VERSION}_Linux_Source.tar.gz"
mkdir -p "$OUT"
rm -f "$OUT/$APP_TGZ" "$OUT/$SRC_TGZ" "$OUT"/*.asc "$OUT/SHA256SUMS.txt"

echo "Packaging Monograph PDF $VERSION (Linux) → $OUT"
# Reproducible-ish archive: fixed owner and sorted names; mtime of the release commit.
STAMP="$(git log -1 --format=%ct HEAD)"
tar --sort=name --owner=0 --group=0 --numeric-owner --mtime="@$STAMP" \
  -C "$ROOT/dist" -cf - MonographPDF | gzip -n -9 > "$OUT/$APP_TGZ"
git archive --format=tar --prefix="MonographPDF_${VERSION}_Linux_Source/" HEAD | gzip -n -9 > "$OUT/$SRC_TGZ"

(cd "$OUT" && sha256sum "$APP_TGZ" "$SRC_TGZ" > SHA256SUMS.txt && sha256sum -c SHA256SUMS.txt)

if [[ -n "$SIGN_KEY" ]]; then
  for f in "$APP_TGZ" "$SRC_TGZ" SHA256SUMS.txt; do
    gpg --batch --yes --local-user "$SIGN_KEY" --armor --detach-sign --output "$OUT/$f.asc" "$OUT/$f"
    gpg --verify "$OUT/$f.asc" "$OUT/$f"
  done
fi
ls -l "$OUT"
