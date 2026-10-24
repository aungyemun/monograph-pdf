#!/usr/bin/env bash
# Package dist/MonographPDF.app into unsigned .app zip, .dmg, and .pkg (macOS first release).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/env/bin/python"
VERSION="$("$PY" scripts/read_version.py | tr -d '[:space:]')"
APP="$ROOT/dist/MonographPDF.app"
OUT="${1:-$ROOT/dist/release}"
IDENTIFIER="com.aungyemun.monographpdf"

if [[ ! -d "$APP" ]]; then
  echo "Missing $APP — run bash scripts/build_app.sh first." >&2
  exit 1
fi

mkdir -p "$OUT"
ZIP="$OUT/MonographPDF_${VERSION}_macOS.zip"
DMG="$OUT/MonographPDF_${VERSION}_macOS.dmg"
PKG="$OUT/MonographPDF_${VERSION}_macOS.pkg"
SUMS="$OUT/SHA256SUMS.txt"

echo "Packaging Monograph PDF $VERSION (unsigned) → $OUT"

rm -f "$ZIP" "$DMG" "$PKG" "$SUMS"

# .app archive (portable drag-to-Applications)
ditto -c -k --keepParent "$APP" "$ZIP"

# .dmg with Applications shortcut
STAGE="$ROOT/build/dmg_stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"
ditto "$APP" "$STAGE/MonographPDF.app"
ln -s /Applications "$STAGE/Applications"
# UDZO compressed image
hdiutil create \
  -volname "Monograph PDF $VERSION" \
  -srcfolder "$STAGE" \
  -ov -format UDZO \
  "$DMG"
rm -rf "$STAGE"

# .pkg → /Applications (unsigned component + product archive)
PKG_ROOT="$ROOT/build/pkg_root"
SCRIPTS_TMP="$ROOT/build/pkg_scripts"
COMPONENT="$ROOT/build/MonographPDF-component.pkg"
rm -rf "$PKG_ROOT" "$SCRIPTS_TMP" "$COMPONENT"
mkdir -p "$PKG_ROOT/Applications" "$SCRIPTS_TMP"
ditto "$APP" "$PKG_ROOT/Applications/MonographPDF.app"
pkgbuild \
  --root "$PKG_ROOT" \
  --identifier "$IDENTIFIER" \
  --version "$VERSION" \
  --install-location / \
  "$COMPONENT"
productbuild \
  --package "$COMPONENT" \
  --identifier "$IDENTIFIER.pkg" \
  --version "$VERSION" \
  "$PKG"
rm -rf "$PKG_ROOT" "$SCRIPTS_TMP" "$COMPONENT"

(
  cd "$OUT"
  shasum -a 256 \
    "MonographPDF_${VERSION}_macOS.zip" \
    "MonographPDF_${VERSION}_macOS.dmg" \
    "MonographPDF_${VERSION}_macOS.pkg" \
    | tee SHA256SUMS.txt
  ls -lh "MonographPDF_${VERSION}_macOS".*
)

echo "Packaged: zip + dmg + pkg (unsigned) for $VERSION"
