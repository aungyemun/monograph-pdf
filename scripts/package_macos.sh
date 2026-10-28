#!/usr/bin/env bash
# Package a completed dist/MonographPDF.app (scripts/build_app.sh) into:
#   MonographPDF_<v>_macOS.pkg   guided Installer.app package → /Applications (upgrades in place)
#   MonographPDF_<v>_macOS.dmg   drag-and-drop disk image with a designed Finder window
#   MonographPDF_<v>_macOS.zip   portable app archive (ditto: metadata, symlinks, signatures)
#   MonographPDF_<v>_macOS_OCR_Corresponding_Source/   verified source for copyleft OCR libraries
#   SHA256SUMS.txt
# then runs scripts/packaging/verify_macos_release.py over the result.
#
# Development mode (default): the ad-hoc-signed app from build_app.sh; the .pkg is unsigned. For
# local testing only — Gatekeeper rejects these on other Macs and nothing is notarized.
#
# Production mode (Developer ID): build_app.sh must have run with MONOGRAPH_MACOS_SIGN_IDENTITY, and
#   MONOGRAPH_MACOS_INSTALLER_IDENTITY  "Developer ID Installer: Name (TEAMID)"   signs the .pkg
#   MONOGRAPH_NOTARY_PROFILE            notarytool keychain profile (xcrun notarytool store-credentials)
# The app, .dmg and .pkg are notarized and stapled, and Gatekeeper must accept all three.
# Set MONOGRAPH_MACOS_SKIP_NOTARIZE=1 only to test signing; the output is then NOT notarized.
#
# Does not re-sign or modify the .app after copying.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/env/bin/python"
VERSION="$("$PY" scripts/read_version.py --platform macos | tr -d '[:space:]')"
APP="$ROOT/dist/MonographPDF.app"
OUT="${1:-$ROOT/dist/release}"
IDENTIFIER="com.aungyemun.monographpdf"
VOLNAME="Monograph PDF $VERSION"
INSTALLER_IDENTITY="${MONOGRAPH_MACOS_INSTALLER_IDENTITY:-}"
NOTARY_PROFILE="${MONOGRAPH_NOTARY_PROFILE:-}"

if [[ ! -d "$APP" ]]; then
  echo "Missing $APP — run bash scripts/build_app.sh first." >&2
  exit 1
fi
if ! codesign --verify --deep --strict "$APP" 2>/dev/null; then
  echo "ERROR: $APP fails codesign --verify --deep --strict. Rebuild with scripts/build_app.sh." >&2
  exit 1
fi

# Which signing mode built the app? (Authority=Developer ID Application… vs. Signature=adhoc)
if codesign -dvv "$APP" 2>&1 | grep -q "^Authority=Developer ID Application"; then
  MODE="production"
  if [[ -z "${MONOGRAPH_MACOS_SIGN_IDENTITY:-}" ]]; then
    echo "ERROR: production app but MONOGRAPH_MACOS_SIGN_IDENTITY is not set (needed to sign the .dmg)." >&2
    exit 1
  fi
  if [[ -z "$INSTALLER_IDENTITY" ]]; then
    echo "ERROR: production app but MONOGRAPH_MACOS_INSTALLER_IDENTITY is not set." >&2
    exit 1
  fi
  if [[ -z "$NOTARY_PROFILE" && "${MONOGRAPH_MACOS_SKIP_NOTARIZE:-}" != "1" ]]; then
    echo "ERROR: production app but MONOGRAPH_NOTARY_PROFILE is not set." >&2
    exit 1
  fi
else
  MODE="development"
  if [[ -n "$INSTALLER_IDENTITY" || -n "$NOTARY_PROFILE" ]]; then
    echo "ERROR: installer identity / notary profile given, but the app is ad-hoc signed." >&2
    echo "       Rebuild with MONOGRAPH_MACOS_SIGN_IDENTITY='Developer ID Application: …'." >&2
    exit 1
  fi
fi

notarize() {  # notarize + staple one file (app zip, dmg or pkg)
  local file="$1" staple_target="${2:-$1}"
  if [[ "$MODE" != "production" || "${MONOGRAPH_MACOS_SKIP_NOTARIZE:-}" == "1" ]]; then
    return 0
  fi
  echo "Notarizing $(basename "$file")…"
  xcrun notarytool submit "$file" --keychain-profile "$NOTARY_PROFILE" --wait --timeout 2h
  xcrun stapler staple "$staple_target"
  xcrun stapler validate "$staple_target"
}

mkdir -p "$OUT" "$ROOT/build"
ZIP="$OUT/MonographPDF_${VERSION}_macOS.zip"
DMG="$OUT/MonographPDF_${VERSION}_macOS.dmg"
PKG="$OUT/MonographPDF_${VERSION}_macOS.pkg"
echo "Packaging Monograph PDF $VERSION ($MODE mode) → $OUT"
rm -f "$ZIP" "$DMG" "$PKG" "$OUT/SHA256SUMS.txt" "$OUT/verification.json"

# Production: the app itself is notarized and stapled first, so every format carries the ticket.
if [[ "$MODE" == "production" ]]; then
  APP_SUBMIT="$ROOT/build/MonographPDF-notarize.zip"
  ditto -c -k --keepParent "$APP" "$APP_SUBMIT"
  notarize "$APP_SUBMIT" "$APP"
  rm -f "$APP_SUBMIT"
fi

# --- zip: ditto keeps permissions, symlinks, extended attributes and signatures
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"

# --- dmg: read-write image → Finder layout → compressed read-only image
hdiutil_retry() {  # hdiutil intermittently fails with "Resource busy" (Spotlight / fseventsd)
  local attempt
  for attempt in 1 2 3 4 5; do
    if hdiutil "$@"; then return 0; fi
    echo "hdiutil $1 failed (attempt $attempt); retrying in $((attempt * 3)) s…" >&2
    sleep $((attempt * 3))
  done
  echo "ERROR: hdiutil $1 failed after 5 attempts." >&2
  return 1
}
STAGE="$ROOT/build/dmg_stage"
RW="$ROOT/build/MonographPDF-rw.dmg"
rm -rf "$STAGE" "$RW"
mkdir -p "$STAGE/.background"
ditto "$APP" "$STAGE/MonographPDF.app"
ln -s /Applications "$STAGE/Applications"
"$PY" scripts/packaging/macos_installer.py dmg-art "$STAGE/.background" >/dev/null
# An empty image, sized with room for the volume icon and Finder's layout file (the compressed
# image does not grow because of the margin), filled after mounting. "-srcfolder" copies through a
# temporary image whose unmount often fails with "Resource busy" while Spotlight indexes it.
STAGE_MB="$(du -sm "$STAGE" | cut -f1)"
hdiutil_retry create -volname "$VOLNAME" -fs HFS+ -type UDIF -size "$((STAGE_MB + 40))m" -ov "$RW"
# Attach under /Volumes (Finder addresses the window by volume name to store the layout).
if [[ -e "/Volumes/$VOLNAME" ]]; then
  echo "ERROR: a volume named \"$VOLNAME\" is already mounted; eject it and run again." >&2
  exit 1
fi
hdiutil_retry attach "$RW" -readwrite -noverify -noautoopen -nobrowse >/dev/null
MNT="/Volumes/$VOLNAME"
if [[ ! -d "$MNT" ]]; then
  echo "ERROR: $RW did not mount at $MNT." >&2
  exit 1
fi
mdutil -i off "$MNT" >/dev/null 2>&1 || true  # keep Spotlight off the installer volume
ditto "$STAGE" "$MNT"
rm -rf "$STAGE"
# Finder needs the volume browsable to store its layout: remount without -nobrowse.
hdiutil_retry detach "$MNT" >/dev/null
hdiutil_retry attach "$RW" -readwrite -noverify -noautoopen >/dev/null
SetFile -a V "$MNT/.background"
if [[ "${MONOGRAPH_DMG_PLAIN:-}" == "1" ]]; then
  echo "WARNING: MONOGRAPH_DMG_PLAIN=1 — no Finder layout (CI without a GUI session)." >&2
else
  "$PY" scripts/packaging/macos_installer.py dmg-layout "$VOLNAME" | osascript
  if [[ ! -f "$MNT/.DS_Store" ]]; then
    echo "ERROR: Finder did not store the DMG window layout (.DS_Store missing)." >&2
    hdiutil detach "$MNT" -force >/dev/null || true
    exit 1
  fi
fi
# Volume icon last: Finder removes .VolumeIcon.icns while it writes the window layout.
cp "$ROOT/resources/icons/macos/monograph_pdf.icns" "$MNT/.VolumeIcon.icns"
SetFile -a V "$MNT/.VolumeIcon.icns"
SetFile -a C "$MNT"
chmod -Rf go-w "$MNT" || true
sync
hdiutil_retry detach "$MNT" >/dev/null
hdiutil_retry convert "$RW" -format UDZO -imagekey zlib-level=9 -ov -o "$DMG"
rm -f "$RW"
if [[ "$MODE" == "production" ]]; then
  codesign --force --sign "$MONOGRAPH_MACOS_SIGN_IDENTITY" --timestamp "$DMG"
fi

# --- pkg: component (installs exactly into /Applications, upgrades in place) + guided distribution
PKG_WORK="$ROOT/build/pkg_work"
rm -rf "$PKG_WORK"
mkdir -p "$PKG_WORK/root/Applications"
# no extended attributes / quarantine: they would become AppleDouble "._" entries in the payload
ditto --noextattr --noqtn "$APP" "$PKG_WORK/root/Applications/MonographPDF.app"
xattr -cr "$PKG_WORK/root"
export COPYFILE_DISABLE=1
pkgbuild --analyze --root "$PKG_WORK/root" "$PKG_WORK/component.plist" >/dev/null
"$PY" scripts/packaging/macos_installer.py component-plist "$PKG_WORK/component.plist"
pkgbuild --root "$PKG_WORK/root" --component-plist "$PKG_WORK/component.plist" \
  --identifier "$IDENTIFIER" --version "$VERSION" --install-location / \
  "$PKG_WORK/MonographPDF-component.pkg"
"$PY" scripts/packaging/macos_installer.py pkg-resources "$PKG_WORK/resources" "$VERSION" >/dev/null
SIGN_PKG=()
if [[ "$MODE" == "production" ]]; then
  SIGN_PKG=(--sign "$INSTALLER_IDENTITY" --timestamp)
fi
productbuild --distribution "$PKG_WORK/distribution.xml" --resources "$PKG_WORK/resources" \
  --package-path "$PKG_WORK" --identifier "$IDENTIFIER.pkg" --version "$VERSION" \
  ${SIGN_PKG[@]+"${SIGN_PKG[@]}"} "$PKG"
rm -rf "$PKG_WORK"

notarize "$DMG"
notarize "$PKG"

# --- corresponding source for the copyleft OCR libraries (GPL/LGPL), rebuilt from the verified
# upstream archives + exact recipes and checked against the hashes recorded in the inventory.
SOURCES="$OUT/MonographPDF_${VERSION}_macOS_OCR_Corresponding_Source"
rm -rf "$SOURCES"
INVENTORY_COPY="$ROOT/build/macos_ocr_sources.json"
cp "$ROOT/scripts/packaging/macos_ocr_sources.json" "$INVENTORY_COPY"
MONOGRAPH_OCR_SOURCE_CACHE="$ROOT/build/macos-ocr-source-cache" \
  "$PY" scripts/packaging/macos_ocr_sources.py sources "$ROOT/tools/ocr-env" "$INVENTORY_COPY" "$SOURCES"
cp "$ROOT/scripts/packaging/macos_ocr_sources.json" "$SOURCES/THIRD_PARTY_OCR_SOURCES.json"

(
  cd "$OUT"
  shasum -a 256 \
    "MonographPDF_${VERSION}_macOS.zip" \
    "MonographPDF_${VERSION}_macOS.dmg" \
    "MonographPDF_${VERSION}_macOS.pkg" \
    "$(basename "$SOURCES")"/*.tar.gz \
    > SHA256SUMS.txt
  cat SHA256SUMS.txt
)

"$PY" scripts/packaging/verify_macos_release.py "$OUT" --mode "$MODE"
echo "Packaged Monograph PDF $VERSION ($MODE): pkg + dmg + zip + corresponding source → $OUT"
if [[ "$MODE" == "development" ]]; then
  echo "Development build: ad-hoc signed, unsigned .pkg, NOT notarized — for local testing only."
fi
