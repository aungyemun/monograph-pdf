#!/usr/bin/env bash
# Build MonographPDF.app via PyInstaller (macOS first release — version from VERSION).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/env/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing ./env. Run bash scripts/setup_env.sh first." >&2
  exit 1
fi
VERSION="$("$PY" scripts/read_version.py | tr -d '[:space:]')"
echo "Building Monograph PDF $VERSION for macOS"

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
if [[ -f "$ICNS_DIR/monograph_pdf.icns" ]]; then
  ICON_ARGS=(--icon "$ICNS_DIR/monograph_pdf.icns")
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
  --add-data "$ROOT/resources:resources" \
  --add-data "$ROOT/docs/USER_GUIDE.md:docs" \
  --add-data "$ROOT/LICENSE.md:." \
  --add-data "$ROOT/THIRD_PARTY_NOTICES.md:." \
  "$ROOT/app/bootstrap.py"

# PyInstaller --windowed on macOS produces dist/MonographPDF.app
APP="$ROOT/dist/MonographPDF.app"
if [[ ! -d "$APP" && -d "$ROOT/dist/MonographPDF" ]]; then
  echo "Wrapping onedir folder into MonographPDF.app"
  mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
  cp -R "$ROOT/dist/MonographPDF/"* "$APP/Contents/MacOS/"
  cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Monograph PDF</string>
  <key>CFBundleDisplayName</key><string>Monograph PDF</string>
  <key>CFBundleIdentifier</key><string>com.aungyemun.monographpdf</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleExecutable</key><string>MonographPDF</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>CFBundleDocumentTypes</key>
  <array><dict>
    <key>CFBundleTypeName</key><string>PDF Document</string>
    <key>CFBundleTypeRole</key><string>Editor</string>
    <key>LSItemContentTypes</key><array><string>com.adobe.pdf</string></array>
  </dict></array>
</dict></plist>
PLIST
fi

if [[ ! -d "$APP" ]]; then
  echo "Build failed: $APP not found" >&2
  exit 1
fi

RES="$APP/Contents/Resources"
MACOS="$APP/Contents/MacOS"
mkdir -p "$RES/engines" "$RES/models" "$MACOS/engines" "$MACOS/models"
if [[ -d "$ROOT/engines/ocr" ]]; then
  rm -rf "$RES/engines/ocr"
  cp -R "$ROOT/engines/ocr" "$RES/engines/ocr"
  ln -sfn "../Resources/engines/ocr" "$MACOS/engines/ocr"
fi
if [[ -d "$ROOT/models/tessdata" ]]; then
  rm -rf "$RES/models/tessdata"
  cp -R "$ROOT/models/tessdata" "$RES/models/tessdata"
  ln -sfn "../Resources/models/tessdata" "$MACOS/models/tessdata"
fi

echo "Built: $APP (macOS first release $VERSION)"
