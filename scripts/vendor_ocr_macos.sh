#!/usr/bin/env bash
# Stage a macOS OCR engine into engines/ocr and tessdata into models/tessdata.
# Everything stays under this project folder (tools/micromamba, tools/ocr-env).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
unset DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH

mkdir -p tools/micromamba tools/ocr-env models/tessdata engines/ocr

# Language data (tessdata_fast 4.1.0)
for lang in eng jpn osd; do
  dest="models/tessdata/${lang}.traineddata"
  if [[ ! -f "$dest" ]]; then
    curl -L --fail -o "$dest" \
      "https://github.com/tesseract-ocr/tessdata_fast/raw/4.1.0/${lang}.traineddata"
  fi
done

MM="$ROOT/tools/micromamba/micromamba"
if [[ ! -x "$MM" ]]; then
  echo "Downloading micromamba into tools/micromamba…"
  curl -L --fail -o /tmp/micromamba-osx-arm64.tar.bz2 \
    "https://micro.mamba.pm/api/micromamba/osx-arm64/latest"
  tar -xjf /tmp/micromamba-osx-arm64.tar.bz2 -C tools/micromamba
  if [[ -x tools/micromamba/bin/micromamba ]]; then
    mv tools/micromamba/bin/micromamba tools/micromamba/micromamba
  fi
fi

if [[ ! -x "$ROOT/tools/ocr-env/bin/tesseract" ]]; then
  echo "Creating tools/ocr-env with conda-forge tesseract…"
  "$MM" create -y -p "$ROOT/tools/ocr-env" -c conda-forge "tesseract=5.5.3"
fi

cat > engines/ocr/tesseract <<'WRAP'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/../.." && pwd)"
export DYLD_LIBRARY_PATH="$ROOT/tools/ocr-env/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
exec "$ROOT/tools/ocr-env/bin/tesseract" "$@"
WRAP
chmod +x engines/ocr/tesseract

if [[ -f third_party/licenses/TESSERACT_NOTICE.txt ]]; then
  cp third_party/licenses/TESSERACT_NOTICE.txt engines/ocr/TESSERACT_NOTICE.txt
fi

engines/ocr/tesseract --version | head -5
echo "OCR staged: engines/ocr + models/tessdata (runtime libs in tools/ocr-env)"
