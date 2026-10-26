#!/usr/bin/env bash
# Build MonographPDF.app via PyInstaller for macOS (platform version from versions/macos.txt).
#
# Order (must not modify the bundle after the final signature):
#   1) PyInstaller onedir/windowed build
#   2) Write Info.plist (version, bundle id, PDF UTI)
#   3) Stage OCR + tessdata into Resources
#   4) Icons / permissions
#   5) Ad-hoc codesign nested Mach-O then the .app
#   6) codesign --verify
#
# Ad-hoc signing (- identity) is for local/dev validation only — not Developer ID / notarization.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/env/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing ./env. Run bash scripts/setup_env.sh first." >&2
  exit 1
fi

# Always the macOS product line (do not pick up Windows root VERSION by accident in CI scripts).
VERSION="$("$PY" scripts/read_version.py --platform macos | tr -d '[:space:]')"
# Numeric CFBundleVersion: major*10000 + minor*100 + patch (0.1.0 → 100).
BUNDLE_VERSION="$("$PY" -c "from core.versioning import parse_version; M,m,p=parse_version('$VERSION'); print(M*10000+m*100+p)")"
IDENTIFIER="com.aungyemun.monographpdf"
echo "Building Monograph PDF $VERSION for macOS (CFBundleVersion=$BUNDLE_VERSION)"

"$PY" scripts/generate_branding_icons.py || true

ICON_SRC="$ROOT/resources/icons/source/monograph_pdf_icon_1024.png"
ICNS_DIR="$ROOT/resources/icons/macos"
mkdir -p "$ICNS_DIR" "$ROOT/build" "$ROOT/dist"
if [[ -f "$ICON_SRC" ]] && command -v iconutil >/dev/null && command -v sips >/dev/null; then
  ICONSET="$ROOT/build/MonographPDF.iconset"
  rm -rf "$ICONSET"
  mkdir -p "$ICONSET"
  sips -z 16 16     "$ICON_SRC" --out "$ICONSET/icon_16x16.png" >/dev/null
  sips -z 32 32     "$ICON_SRC" --out "$ICONSET/icon_16x16@2x.png" >/dev/null
  sips -z 32 32     "$ICON_SRC" --out "$ICONSET/icon_32x32.png" >/dev/null
  sips -z 64 64     "$ICON_SRC" --out "$ICONSET/icon_32x32@2x.png" >/dev/null
  sips -z 128 128   "$ICON_SRC" --out "$ICONSET/icon_128x128.png" >/dev/null
  sips -z 256 256   "$ICON_SRC" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
  sips -z 256 256   "$ICON_SRC" --out "$ICONSET/icon_256x256.png" >/dev/null
  sips -z 512 512   "$ICON_SRC" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
  sips -z 512 512   "$ICON_SRC" --out "$ICONSET/icon_512x512.png" >/dev/null
  sips -z 1024 1024 "$ICON_SRC" --out "$ICONSET/icon_512x512@2x.png" >/dev/null
  iconutil -c icns "$ICONSET" -o "$ICNS_DIR/monograph_pdf.icns"
fi

ICON_ARGS=()
ICNS="$ICNS_DIR/monograph_pdf.icns"
if [[ -f "$ICNS" ]]; then
  ICON_ARGS=(--icon "$ICNS")
fi

"$PY" -m PyInstaller \
  --noconfirm \
  --clean \
  --name MonographPDF \
  --onedir \
  --windowed \
  "${ICON_ARGS[@]}" \
  --distpath "$ROOT/dist" \
  --workpath "$ROOT/build/pyinstaller" \
  --specpath "$ROOT/build" \
  --paths "$ROOT" \
  --hidden-import=fitz \
  --hidden-import=engines.mupdf_backend \
  --hidden-import=engines.bake_edits \
  --hidden-import=core.document \
  --hidden-import=core.editing.edit_model \
  --hidden-import=core.product_meta \
  --hidden-import=core.ocr \
  --hidden-import=core.ocr.engine \
  --hidden-import=core.ocr.pipeline \
  --hidden-import=core.ocr.analysis \
  --hidden-import=core.ocr.paths \
  --hidden-import=core.organize \
  --hidden-import=core.convert \
  --collect-submodules=core \
  --collect-submodules=ui \
  --hidden-import=docx \
  --hidden-import=pdf2docx \
  --collect-submodules=pdf2docx \
  --hidden-import=cv2 \
  --hidden-import=fontTools \
  --hidden-import=numpy \
  --hidden-import=app.smoke_test \
  --hidden-import=openpyxl \
  --hidden-import=pptx \
  --hidden-import=PIL \
  --hidden-import=PySide6.QtPrintSupport \
  --collect-all=pymupdf \
  --exclude-module=tkinter \
  --exclude-module=matplotlib \
  --add-data "$ROOT/VERSION:." \
  --add-data "$ROOT/versions:versions" \
  --add-data "$ROOT/resources:resources" \
  --add-data "$ROOT/docs/USER_GUIDE.md:docs" \
  --add-data "$ROOT/LICENSE.md:." \
  --add-data "$ROOT/THIRD_PARTY_NOTICES.md:." \
  "$ROOT/app/bootstrap.py"

APP="$ROOT/dist/MonographPDF.app"
if [[ ! -d "$APP" && -d "$ROOT/dist/MonographPDF" ]]; then
  echo "Wrapping onedir folder into MonographPDF.app"
  mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
  cp -R "$ROOT/dist/MonographPDF/"* "$APP/Contents/MacOS/"
fi

if [[ ! -d "$APP" ]]; then
  echo "Build failed: $APP not found" >&2
  exit 1
fi

RES="$APP/Contents/Resources"
MACOS_DIR="$APP/Contents/MacOS"
mkdir -p "$RES" "$MACOS_DIR"

# --- Info.plist (always rewrite; PyInstaller defaults leave 0.0.0 / weak identifiers) ---
if [[ -f "$ICNS" ]]; then
  cp "$ICNS" "$RES/monograph_pdf.icns"
  ICON_FILE="monograph_pdf.icns"
else
  ICON_FILE=""
fi

"$PY" - <<PY
from pathlib import Path
import plistlib
app = Path(r"""$APP""")
plist_path = app / "Contents" / "Info.plist"
data = {}
if plist_path.is_file():
    with plist_path.open("rb") as fh:
        data = plistlib.load(fh)
data.update({
    "CFBundleName": "Monograph PDF",
    "CFBundleDisplayName": "Monograph PDF",
    "CFBundleIdentifier": "$IDENTIFIER",
    "CFBundleVersion": "$BUNDLE_VERSION",
    "CFBundleShortVersionString": "$VERSION",
    "CFBundleExecutable": "MonographPDF",
    "CFBundlePackageType": "APPL",
    "LSMinimumSystemVersion": "13.0",
    "NSHighResolutionCapable": True,
    "CFBundleDocumentTypes": [{
        "CFBundleTypeName": "PDF Document",
        "CFBundleTypeRole": "Editor",
        "LSItemContentTypes": ["com.adobe.pdf"],
        "CFBundleTypeExtensions": ["pdf"],
    }],
})
icon = "$ICON_FILE"
if icon:
    data["CFBundleIconFile"] = icon
with plist_path.open("wb") as fh:
    plistlib.dump(data, fh)
print("Wrote", plist_path, "version", data["CFBundleShortVersionString"])
PY

# --- Stage OCR / tessdata BEFORE any final signature ---
mkdir -p "$RES/engines" "$RES/models" "$MACOS_DIR/engines" "$MACOS_DIR/models"
if [[ -d "$ROOT/engines/ocr" ]]; then
  rm -rf "$RES/engines/ocr"
  cp -R "$ROOT/engines/ocr" "$RES/engines/ocr"
  ln -sfn "../Resources/engines/ocr" "$MACOS_DIR/engines/ocr"
fi
if [[ -d "$ROOT/models/tessdata" ]]; then
  rm -rf "$RES/models/tessdata"
  cp -R "$ROOT/models/tessdata" "$RES/models/tessdata"
  ln -sfn "../Resources/models/tessdata" "$MACOS_DIR/models/tessdata"
fi

# Executable bit on the launcher
if [[ -f "$MACOS_DIR/MonographPDF" ]]; then
  chmod a+x "$MACOS_DIR/MonographPDF"
fi

# --- Ad-hoc codesign (nested Mach-O first, then bundle). Do not modify the .app after this. ---
sign_file() {
  local target="$1"
  codesign --force --sign - --timestamp=none --identifier "$IDENTIFIER" "$target" 2>/dev/null \
    || codesign --force --sign - --timestamp=none "$target"
}

# dylib / so / bundle binaries inside the app (innermost → outer)
while IFS= read -r -d '' f; do
  sign_file "$f"
done < <(find "$APP" \( -name "*.dylib" -o -name "*.so" -o -name "*.bundle" \) -type f -print0 2>/dev/null || true)

# Framework binaries
while IFS= read -r -d '' fw; do
  bin="$fw/Versions/Current/$(basename "${fw%.framework}")"
  if [[ -f "$bin" ]]; then
    sign_file "$bin"
  fi
  sign_file "$fw"
done < <(find "$APP" -name "*.framework" -type d -print0 2>/dev/null || true)

# Main executable then the .app itself
if [[ -f "$MACOS_DIR/MonographPDF" ]]; then
  sign_file "$MACOS_DIR/MonographPDF"
fi
codesign --force --sign - --timestamp=none --identifier "$IDENTIFIER" "$APP"

echo "Verifying ad-hoc signature…"
codesign --verify --verbose=2 "$APP"
codesign -dv --verbose=2 "$APP" 2>&1 | head -20

# Confirm Info.plist version survived signing
SHORT="$("$PY" -c "import plistlib; print(plistlib.load(open('$APP/Contents/Info.plist','rb'))['CFBundleShortVersionString'])")"
if [[ "$SHORT" != "$VERSION" ]]; then
  echo "ERROR: CFBundleShortVersionString is '$SHORT', expected '$VERSION'" >&2
  exit 1
fi

echo "Built: $APP (macOS $VERSION, ad-hoc signed — not Developer ID / not notarized)"
