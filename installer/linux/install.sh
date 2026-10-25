#!/usr/bin/env bash
# Per-user Linux install of a built MonographPDF tree (dist/MonographPDF or similar).
# Usage: bash installer/linux/install.sh /path/to/MonographPDF
set -euo pipefail
SRC="${1:-}"
if [[ -z "$SRC" || ! -d "$SRC" ]]; then
  echo "Usage: $0 /path/to/MonographPDF  (folder containing MonographPDF binary)" >&2
  exit 2
fi
SRC="$(cd "$SRC" && pwd)"
VERSION="$(cat "$SRC/VERSION" 2>/dev/null || echo unknown)"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/Monograph PDF"
BIN="${XDG_BIN_HOME:-$HOME/.local/bin}"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

mkdir -p "$DEST" "$BIN" "$APPS"
rsync -a --delete --exclude 'runtime' "$SRC/" "$DEST/"
printf '%s\n' "{\"scope\":\"user\",\"version\":\"$VERSION\"}" > "$DEST/.monograph-installed"
chmod +x "$DEST/MonographPDF" 2>/dev/null || true
ln -sfn "$DEST/MonographPDF" "$BIN/MonographPDF"

ICON=""
for cand in \
  "$DEST/resources/icons/windows/monograph_pdf_256.png" \
  "$DEST/resources/icons/source/monograph_pdf_icon_1024.png"; do
  [[ -f "$cand" ]] && ICON="$cand" && break
done
cat > "$APPS/monograph-pdf.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Monograph PDF
Comment=Offline privacy-focused PDF editor
Exec="$DEST/MonographPDF" %F
Icon=${ICON:-monograph-pdf}
Terminal=false
Categories=Office;Viewer;Graphics;
MimeType=application/pdf;
StartupWMClass=MonographPDF
EOF
chmod +x "$APPS/monograph-pdf.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" || true
command -v xdg-mime >/dev/null && xdg-mime default monograph-pdf.desktop application/pdf || true

cat > "$DEST/uninstall.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
rm -f "$BIN/MonographPDF" "$APPS/monograph-pdf.desktop"
rm -rf "$DEST"
echo "Monograph PDF removed. Settings in ~/.local/share/monograph-pdf were kept."
EOF
chmod +x "$DEST/uninstall.sh"
echo "Installed to $DEST"
echo "Launcher: $BIN/MonographPDF"
echo "Uninstall: $DEST/uninstall.sh"
