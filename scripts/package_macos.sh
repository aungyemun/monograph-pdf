#!/usr/bin/env bash
# Package a completed (ad-hoc-signed) dist/MonographPDF.app into zip / dmg / pkg.
# Does not re-sign or modify the .app after copying — build_app.sh must finish first.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/env/bin/python"
VERSION="$("$PY" scripts/read_version.py --platform macos | tr -d '[:space:]')"
APP="$ROOT/dist/MonographPDF.app"
OUT="${1:-$ROOT/dist/release}"
IDENTIFIER="com.aungyemun.monographpdf"

if [[ ! -d "$APP" ]]; then
  echo "Missing $APP — run bash scripts/build_app.sh first." >&2
  exit 1
fi

# Refuse to package a bundle whose signature was invalidated after OCR staging.
if ! codesign --verify "$APP" 2>/dev/null; then
  echo "ERROR: $APP fails codesign --verify. Rebuild with scripts/build_app.sh (OCR must be staged before signing)." >&2
  exit 1
fi

mkdir -p "$OUT"
ZIP="$OUT/MonographPDF_${VERSION}_macOS.zip"
DMG="$OUT/MonographPDF_${VERSION}_macOS.dmg"
PKG="$OUT/MonographPDF_${VERSION}_macOS.pkg"

echo "Packaging Monograph PDF $VERSION (ad-hoc-signed .app; not Developer ID) → $OUT"
rm -f "$ZIP" "$DMG" "$PKG" "$OUT/SHA256SUMS.txt"

ditto -c -k --keepParent "$APP" "$ZIP"

STAGE="$ROOT/build/dmg_stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"
ditto "$APP" "$STAGE/MonographPDF.app"
ln -s /Applications "$STAGE/Applications"
# hdiutil intermittently fails with "Resource busy" while Spotlight/fseventsd still holds the
# temporary volume; retry a few times before giving up.
for attempt in 1 2 3 4 5; do
  if hdiutil create -volname "Monograph PDF $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG"; then
    break
  fi
  if [[ "$attempt" == 5 ]]; then
    echo "ERROR: hdiutil create failed after $attempt attempts." >&2
    exit 1
  fi
  echo "hdiutil create failed (attempt $attempt); retrying in $((attempt * 3)) s…" >&2
  sleep $((attempt * 3))
done
rm -rf "$STAGE"

PKG_ROOT="$ROOT/build/pkg_root"
COMPONENT="$ROOT/build/MonographPDF-component.pkg"
rm -rf "$PKG_ROOT" "$COMPONENT"
mkdir -p "$PKG_ROOT/Applications"
ditto "$APP" "$PKG_ROOT/Applications/MonographPDF.app"
pkgbuild --root "$PKG_ROOT" --identifier "$IDENTIFIER" --version "$VERSION" --install-location / "$COMPONENT"
productbuild --package "$COMPONENT" --identifier "$IDENTIFIER.pkg" --version "$VERSION" "$PKG"
rm -rf "$PKG_ROOT" "$COMPONENT"

# Confirm extracted zip still verifies
EXTRACT="$ROOT/build/zip_verify"
rm -rf "$EXTRACT"
mkdir -p "$EXTRACT"
ditto -x -k "$ZIP" "$EXTRACT"
codesign --verify "$EXTRACT/MonographPDF.app"

(
  cd "$OUT"
  shasum -a 256 \
    "MonographPDF_${VERSION}_macOS.zip" \
    "MonographPDF_${VERSION}_macOS.dmg" \
    "MonographPDF_${VERSION}_macOS.pkg" \
    | tee SHA256SUMS.txt
  ls -lh "MonographPDF_${VERSION}_macOS".*
)

echo "Packaged: zip + dmg + pkg for $VERSION (ad-hoc signature intact after zip extract)"
