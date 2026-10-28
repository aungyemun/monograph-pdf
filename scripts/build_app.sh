#!/usr/bin/env bash
# Build MonographPDF.app via PyInstaller for macOS (platform version from versions/macos.txt).
#
# Order (must not modify the bundle after the final signature):
#   1) PyInstaller onedir/windowed build
#   2) Write Info.plist (version, bundle id, PDF UTI)
#   3) Stage OCR + tessdata into Resources
#   4) Icons / permissions
#   5) Codesign nested Mach-O then the .app
#   6) codesign --verify
#
# Signing modes:
#   development (default)  ad-hoc ("-") for local testing only — not Developer ID / not notarized.
#                          The OCR engine keeps its published conda-forge signatures.
#   production             MONOGRAPH_MACOS_SIGN_IDENTITY="Developer ID Application: Name (TEAMID)"
#                          Hardened Runtime + secure timestamp + installer/macos/entitlements.plist
#                          on every Mach-O, the OCR engine included (required for notarization);
#                          its provenance is checked against the inventory before signing.
#                          scripts/package_macos.sh then notarizes and staples.
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
    # Base names match the bundle's file name (MonographPDF.app, the path earlier versions used);
    # en.lproj/InfoPlist.strings gives the name people see, "Monograph PDF", in the Dock, menu bar,
    # Finder, Spotlight and Launchpad (Finder only localizes when the file name equals the base name).
    "CFBundleName": "MonographPDF",
    "CFBundleDisplayName": "MonographPDF",
    "CFBundleIdentifier": "$IDENTIFIER",
    "CFBundleVersion": "$BUNDLE_VERSION",
    "CFBundleShortVersionString": "$VERSION",
    "CFBundleExecutable": "MonographPDF",
    "CFBundlePackageType": "APPL",
    "LSMinimumSystemVersion": "13.0",
    "LSArchitecturePriority": ["arm64"],
    "LSHasLocalizedDisplayName": True,
    "CFBundleDevelopmentRegion": "en",
    "LSApplicationCategoryType": "public.app-category.productivity",
    "NSHumanReadableCopyright": "© 2026 Aung Ye Mun. AGPL-3.0-or-later.",
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

mkdir -p "$RES/en.lproj"
printf '"CFBundleDisplayName" = "Monograph PDF";\n"CFBundleName" = "Monograph PDF";\n' > "$RES/en.lproj/InfoPlist.strings"

# --- Stage OCR / tessdata BEFORE any final signature ---
mkdir -p "$RES/engines" "$RES/models" "$MACOS_DIR/engines" "$MACOS_DIR/models"
# engines/ocr/tesseract in the source tree is a dev wrapper into tools/ocr-env (never bundled),
# so stage the real binary and its dylib closure instead. Symlinks live in Contents/MacOS/<dir>/,
# hence two levels up to reach Contents/Resources.
if [[ -x "$ROOT/tools/ocr-env/bin/tesseract" ]]; then
  "$PY" scripts/packaging/stage_ocr_macos.py "$ROOT/tools/ocr-env" "$RES/engines/ocr"
  ln -sfn "../../Resources/engines/ocr" "$MACOS_DIR/engines/ocr"
else
  echo "WARNING: tools/ocr-env missing — OCR will be unavailable in this build (run scripts/vendor_ocr_macos.sh)." >&2
fi
if [[ -d "$ROOT/models/tessdata" ]]; then
  rm -rf "$RES/models/tessdata"
  cp -R "$ROOT/models/tessdata" "$RES/models/tessdata"
  ln -sfn "../../Resources/models/tessdata" "$MACOS_DIR/models/tessdata"
fi
# Fail the build on any dangling symlink inside the bundle.
DANGLING="$(find "$APP" -type l ! -exec test -e {} \; -print)"
if [[ -n "$DANGLING" ]]; then
  echo "ERROR: dangling symlinks in bundle:" >&2
  echo "$DANGLING" >&2
  exit 1
fi
# OCR provenance: the staged engine must equal the recorded inventory byte for byte, with every
# package's license present (scripts/packaging/macos_ocr_sources.py; corresponding source is
# produced and checked by package_macos.sh).
if [[ -d "$RES/engines/ocr/bin" ]]; then
  cp "$ROOT/scripts/packaging/macos_ocr_sources.json" "$RES/engines/ocr/THIRD_PARTY_OCR_SOURCES.json"
  "$PY" scripts/packaging/macos_ocr_sources.py check "$RES/engines/ocr" \
    "$ROOT/scripts/packaging/macos_ocr_sources.json" ""
fi
# No builder-specific paths (home folder, checkout) may ship inside the app.
LEAKS="$(grep -rlF -- "$HOME/" "$APP" 2>/dev/null || true)"
if [[ -n "$LEAKS" ]]; then
  echo "ERROR: the bundle contains the builder's home path ($HOME):" >&2
  echo "$LEAKS" >&2
  exit 1
fi

# Executable bit on the launcher
if [[ -f "$MACOS_DIR/MonographPDF" ]]; then
  chmod a+x "$MACOS_DIR/MonographPDF"
fi

# --- Codesign (nested Mach-O first, then bundle). Do not modify the .app after this. ---
SIGN_IDENTITY="${MONOGRAPH_MACOS_SIGN_IDENTITY:--}"
ENTITLEMENTS="$ROOT/installer/macos/entitlements.plist"
if [[ "$SIGN_IDENTITY" == "-" ]]; then
  SIGN_MODE="development"
  SIGN_OPTS=(--timestamp=none)
else
  SIGN_MODE="production"
  if ! security find-identity -v -p codesigning | grep -qF "$SIGN_IDENTITY"; then
    echo "ERROR: signing identity not found in the keychain: $SIGN_IDENTITY" >&2
    exit 1
  fi
  SIGN_OPTS=(--timestamp --options runtime)
fi
echo "Signing mode: $SIGN_MODE"
sign_file() {
  local target="$1"
  codesign --force --sign "$SIGN_IDENTITY" "${SIGN_OPTS[@]}" --identifier "$IDENTIFIER" "$target" 2>/dev/null \
    || codesign --force --sign "$SIGN_IDENTITY" "${SIGN_OPTS[@]}" "$target"
}

# dylib / so / bundle binaries inside the app (innermost → outer). In development the OCR engine
# keeps the conda-forge ad-hoc signatures it was published with, so its bytes stay identical to the
# inventoried packages (macos_ocr_sources.json); those signatures are verified instead.
while IFS= read -r -d '' f; do
  if [[ "$SIGN_MODE" == "development" ]]; then
    case "$f" in "$RES/engines/ocr/"*) continue ;; esac
  fi
  sign_file "$f"
done < <(find "$APP" \( -name "*.dylib" -o -name "*.so" -o -name "*.bundle" \) -type f -print0 2>/dev/null || true)
if [[ "$SIGN_MODE" == "production" && -f "$RES/engines/ocr/bin/tesseract" ]]; then
  sign_file "$RES/engines/ocr/bin/tesseract"
fi
while IFS= read -r -d '' f; do
  codesign --verify --strict "$f" || { echo "ERROR: invalid signature on bundled OCR file $f" >&2; exit 1; }
done < <(find "$RES/engines/ocr/bin" "$RES/engines/ocr/lib" -type f -print0 2>/dev/null || true)

# Framework binaries
while IFS= read -r -d '' fw; do
  bin="$fw/Versions/Current/$(basename "${fw%.framework}")"
  if [[ -f "$bin" ]]; then
    sign_file "$bin"
  fi
  sign_file "$fw"
done < <(find "$APP" -name "*.framework" -type d -print0 2>/dev/null || true)

# Main executable then the .app itself (entitlements only on the main executable and the bundle)
ENT_OPTS=()
if [[ "$SIGN_MODE" == "production" ]]; then
  ENT_OPTS=(--entitlements "$ENTITLEMENTS")
fi
if [[ -f "$MACOS_DIR/MonographPDF" ]]; then
  codesign --force --sign "$SIGN_IDENTITY" "${SIGN_OPTS[@]}" ${ENT_OPTS[@]+"${ENT_OPTS[@]}"} \
    --identifier "$IDENTIFIER" "$MACOS_DIR/MonographPDF"
fi
codesign --force --sign "$SIGN_IDENTITY" "${SIGN_OPTS[@]}" ${ENT_OPTS[@]+"${ENT_OPTS[@]}"} \
  --identifier "$IDENTIFIER" "$APP"

echo "Verifying $SIGN_MODE signature…"
codesign --verify --deep --strict --verbose=2 "$APP"
codesign -dv --verbose=2 "$APP" 2>&1 | head -20

# The bundled OCR engine must run from inside the app with no project tools/ on the path.
if [[ -x "$RES/engines/ocr/bin/tesseract" ]]; then
  env -u DYLD_LIBRARY_PATH -u DYLD_FALLBACK_LIBRARY_PATH "$RES/engines/ocr/bin/tesseract" --version | head -1
  BAD_REFS="$(otool -L "$RES/engines/ocr/bin/tesseract" "$RES/engines/ocr/lib/"*.dylib | grep -E '^\s+/' | grep -vE '^\s+(/usr/lib/|/System/)' || true)"
  if [[ -n "$BAD_REFS" ]]; then
    echo "ERROR: bundled OCR links outside the app:" >&2
    echo "$BAD_REFS" >&2
    exit 1
  fi
fi

# Confirm Info.plist version survived signing
SHORT="$("$PY" -c "import plistlib; print(plistlib.load(open('$APP/Contents/Info.plist','rb'))['CFBundleShortVersionString'])")"
if [[ "$SHORT" != "$VERSION" ]]; then
  echo "ERROR: CFBundleShortVersionString is '$SHORT', expected '$VERSION'" >&2
  exit 1
fi

if [[ "$SIGN_MODE" == "production" ]]; then
  echo "Built: $APP (macOS $VERSION, Developer ID signed, Hardened Runtime — not yet notarized)"
else
  echo "Built: $APP (macOS $VERSION, ad-hoc signed — not Developer ID / not notarized)"
fi
