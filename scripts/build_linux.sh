#!/usr/bin/env bash
# Build dist/MonographPDF (PyInstaller onedir) for Linux x86_64 (version from versions/linux.txt).
#
# Order:
#   1) PyInstaller onedir/windowed build
#   2) Bundle Tesseract (binary + its non-glibc shared libraries) under engines/ocr
#   3) Copy pinned tessdata (eng/jpn/osd) under models/tessdata
#   4) Linux VERSION file, installer helper, end-user docs
#   5) Offscreen smoke test of the built binary
#
# Tesseract comes from engines/ocr/tesseract as staged by scripts/vendor_ocr.sh (a symlink to
# the system or micromamba binary). The copy in dist is relinked with RPATH $ORIGIN/../lib so it
# never loads libraries from the build machine's prefix.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/env/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing ./env. Run bash scripts/setup_env.sh first." >&2
  exit 1
fi
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "build_linux.sh builds the Linux app only." >&2
  exit 1
fi
for tool in patchelf ldd; do
  command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 1; }
done

# Always the Linux product line (root VERSION mirrors Windows).
VERSION="$("$PY" scripts/read_version.py --platform linux | tr -d '[:space:]')"
echo "Building Monograph PDF $VERSION for Linux"

TESS_SRC="$ROOT/engines/ocr/tesseract"
if [[ ! -e "$TESS_SRC" ]]; then
  echo "OCR engine not staged. Run bash scripts/vendor_ocr.sh first." >&2
  exit 1
fi
TESS_SRC="$(readlink -f "$TESS_SRC")"
"$PY" scripts/ci/stage_ocr_engine_linux.py --verify-tessdata

DIST="$ROOT/dist/MonographPDF"
rm -rf "$DIST"
mkdir -p "$ROOT/build" "$ROOT/dist"

"$PY" -m PyInstaller \
  --noconfirm \
  --clean \
  --name MonographPDF \
  --onedir \
  --windowed \
  --distpath "$ROOT/dist" \
  --workpath "$ROOT/build/pyinstaller-linux" \
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
  --add-data "$ROOT/versions:versions" \
  --add-data "$ROOT/resources:resources" \
  --add-data "$ROOT/docs/USER_GUIDE.md:docs" \
  --add-data "$ROOT/LICENSE.md:." \
  --add-data "$ROOT/THIRD_PARTY_NOTICES.md:." \
  "$ROOT/app/bootstrap.py"

if [[ ! -x "$DIST/MonographPDF" ]]; then
  echo "Build failed: $DIST/MonographPDF not found" >&2
  exit 1
fi

# --- OCR engine: binary + shared libraries outside glibc ---
OCR="$DIST/engines/ocr"
mkdir -p "$OCR/bin" "$OCR/lib"
cp -L "$TESS_SRC" "$OCR/bin/tesseract"
chmod 0755 "$OCR/bin/tesseract"
is_system_lib() {
  case "$(basename "$1")" in
    ld-linux*|libc.so*|libm.so*|libdl.so*|libpthread.so*|librt.so*|libresolv.so*|libutil.so*) return 0 ;;
  esac
  return 1
}
while read -r lib; do
  [[ -n "$lib" && -f "$lib" ]] || continue
  is_system_lib "$lib" && continue
  name="$(basename "$lib")"
  cp -L "$lib" "$OCR/lib/$name"
  chmod 0644 "$OCR/lib/$name"
done < <(ldd "$TESS_SRC" | awk '/=> \// {print $3}')
patchelf --set-rpath '$ORIGIN/../lib' "$OCR/bin/tesseract"
for so in "$OCR"/lib/*.so*; do
  patchelf --set-rpath '$ORIGIN' "$so" 2>/dev/null || true
done
if ldd "$OCR/bin/tesseract" | grep -E "not found|$(dirname "$(dirname "$TESS_SRC")")" ; then
  echo "ERROR: bundled tesseract still resolves libraries outside the bundle" >&2
  exit 1
fi
"$OCR/bin/tesseract" --version | head -1

mkdir -p "$DIST/models"
cp -R "$ROOT/models/tessdata" "$DIST/models/tessdata"

# --- Linux version, installer helper and end-user docs beside the binary ---
printf '%s\n' "$VERSION" > "$DIST/VERSION"
cp "$ROOT/installer/linux/install.sh" "$DIST/install.sh"
chmod 0755 "$DIST/install.sh" "$DIST/MonographPDF"
for doc in README.md LINUX.md LICENSE LICENSE.md THIRD_PARTY_NOTICES.md SECURITY.md CITATION.cff CHANGELOG.md; do
  cp "$ROOT/$doc" "$DIST/$doc"
done
mkdir -p "$DIST/licenses"
cp -R "$ROOT/licenses/." "$DIST/licenses/"

# --- Smoke test of the built binary (offscreen, isolated runtime folder) ---
SMOKE_RT="$(mktemp -d)"
trap 'rm -rf "$SMOKE_RT"' EXIT
QT_QPA_PLATFORM=offscreen MONOGRAPH_PDF_HEADLESS=1 \
  "$DIST/MonographPDF" --runtime-dir "$SMOKE_RT" --smoke-test
echo "Built: $DIST (Linux $VERSION)"
