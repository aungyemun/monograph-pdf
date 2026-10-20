# Build canonical ./MonographPDF.exe via PyInstaller into project root.
# Uses --onedir (exe + _internal/) for fast cold start — avoids onefile temp extraction.
# Intermediates: ./build  Distributable also under ./dist/MonographPDF/
# Usage: powershell -ExecutionPolicy Bypass -File scripts/build_exe.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Py = Join-Path $Root "env\Scripts\python.exe"

# Controlled build PATH: PyInstaller's Qt hook copies OpenSSL DLLs it finds on PATH into the bundle. Drop every
# PATH folder outside Windows and the project that holds one (typically Git for Windows' mingw64in) so the
# build does not depend on what else is installed. check_release.py prune removes any that still slip in.
$kept = @()
foreach ($dir in ($env:PATH -split ';')) {
    if (-not $dir) { continue }
    $isWindows = $dir.StartsWith($env:SystemRoot, [System.StringComparison]::OrdinalIgnoreCase)
    $hasOpenSsl = (Test-Path (Join-Path $dir "libssl-3-x64.dll")) -or (Test-Path (Join-Path $dir "libcrypto-3-x64.dll"))
    if ($hasOpenSsl -and -not $isWindows -and -not $dir.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-Host "Build PATH: ignoring $dir (contains OpenSSL DLLs)"
        continue
    }
    $kept += $dir
}
$env:PATH = $kept -join ';'

if (-not (Test-Path $Py)) {
    Write-Error "Missing ./env. Run scripts/setup_env.ps1 first."
}

$Version = (& $Py "scripts\read_version.py").Trim()
Write-Host "Building Monograph PDF $Version"

New-Item -ItemType Directory -Force -Path "$Root\build", "$Root\dist" | Out-Null

# Branding icons from resources\icons\source\Monograph_PDF_logo.png (offline, Pillow)
& $Py "$Root\scripts\generate_branding_icons.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Icon = Join-Path $Root "resources\icons\windows\monograph_pdf.ico"
if (-not (Test-Path $Icon)) {
    Write-Error "Missing application icon: $Icon"
}

& $Py "$Root\scripts\make_version_info.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$VersionInfo = Join-Path $Root "build\version_info.txt"

# OCR engine + tessdata ship as sidecars next to MonographPDF.exe (engines/ocr, models/tessdata).
# They are not downloaded at runtime. Keep them beside the exe for offline OCR.
& $Py -m PyInstaller `
    --noconfirm `
    --clean `
    --name MonographPDF `
    --onedir `
    --windowed `
    --icon "$Icon" `
    --version-file "$VersionInfo" `
    --distpath "$Root\dist" `
    --workpath "$Root\build\pyinstaller" `
    --specpath "$Root\build" `
    --paths "$Root" `
    --hidden-import=fitz `
    --hidden-import=engines.mupdf_backend `
    --hidden-import=engines.bake_edits `
    --hidden-import=core.document `
    --hidden-import=core.editing.edit_model `
    --hidden-import=core.product_meta `
    --hidden-import=core.ocr `
    --hidden-import=core.ocr.engine `
    --hidden-import=core.ocr.pipeline `
    --hidden-import=core.ocr.analysis `
    --hidden-import=core.ocr.paths `
    --hidden-import=core.organize `
    --hidden-import=core.organize.page_ops `
    --hidden-import=core.organize.merge `
    --hidden-import=core.organize.split `
    --hidden-import=core.organize.temputil `
    --hidden-import=core.convert `
    --collect-submodules=core `
    --collect-submodules=ui `
    --copy-metadata=pyinstaller `
    --hidden-import=docx `
    --hidden-import=pdf2docx `
    --collect-submodules=pdf2docx `
    --hidden-import=cv2 `
    --hidden-import=fontTools `
    --hidden-import=numpy `
    --hidden-import=app.smoke_test `
    --hidden-import=core.convert.office_bridge `
    --hidden-import=core.convert.office_to_pdf `
    --hidden-import=core.convert.pdf_to_docx `
    --hidden-import=ui.task_runner `
    --exclude-module=tkinter `
    --exclude-module=matplotlib `
    --hidden-import=openpyxl `
    --hidden-import=pptx `
    --hidden-import=PIL `
    --hidden-import=core.annotations `
    --hidden-import=core.security `
    --hidden-import=core.redaction `
    --hidden-import=core.signatures `
    --hidden-import=core.printing `
    --hidden-import=PySide6.QtPrintSupport `
    --collect-all=pymupdf `
    --add-data "$Root\VERSION;." `
    --add-data "$Root\resources;resources" `
    --add-data "$Root\docs\USER_GUIDE.md;docs" `
    --add-data "$Root\LICENSE.md;." `
    --add-data "$Root\THIRD_PARTY_NOTICES.md;." `
    "$Root\app\bootstrap.py"

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$OutDir = Join-Path $Root "dist\MonographPDF"
$OutExe = Join-Path $OutDir "MonographPDF.exe"
$OutInternal = Join-Path $OutDir "_internal"
if (-not (Test-Path $OutExe)) { Write-Error "Missing $OutExe" }
if (-not (Test-Path $OutInternal)) { Write-Error "Missing $OutInternal" }

# Remove bundled parts Monograph PDF never uses (network/TLS plugins, Qt Quick/QML, Qt's PDF plugin,
# FFmpeg video I/O, software OpenGL, Python's SSL module); fails if a remaining DLL still needs one.
& $Py "$Root\scripts\packaging\check_release.py" prune $OutDir
if ($LASTEXITCODE -ne 0) { Write-Error "Pruning the bundle failed (see above)." }

# Install at project root: MonographPDF.exe + _internal/ (onedir layout)
if (Test-Path "$Root\_internal") {
    Remove-Item -Recurse -Force "$Root\_internal"
}
Copy-Item -Force $OutExe "$Root\MonographPDF.exe"
# A PDF_editor.exe left at the project root by a PDF Editor (<= 0.1.5) build is stale
Remove-Item -Force "$Root\PDF_editor.exe" -ErrorAction SilentlyContinue
Copy-Item -Recurse -Force $OutInternal "$Root\_internal"

# OCR + tessdata into the onedir payload only (never onto the project-root source trees).
foreach ($Side in @("engines\ocr", "models\tessdata")) {
    $Src = Join-Path $Root $Side
    if (-not (Get-ChildItem (Join-Path $Src "*") -File -Exclude ".gitkeep" -ErrorAction SilentlyContinue)) {
        Write-Warning "Missing OCR files in $Src — run scripts\vendor_ocr.ps1 before packaging."
        continue
    }
    $Dst = Join-Path $OutDir $Side
    Remove-Item -Recurse -Force $Dst -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $Dst | Out-Null
    Copy-Item (Join-Path $Src "*") $Dst -Recurse -Force -Exclude ".gitkeep"
}
$Notice = Join-Path $Root "third_party\licenses\TESSERACT_NOTICE.txt"
if (Test-Path $Notice) {
    $OcrDst = Join-Path $OutDir "engines\ocr"
    if (Test-Path $OcrDst) {
        Copy-Item $Notice (Join-Path $OcrDst "TESSERACT_NOTICE.txt") -Force
    }
}

Write-Host "Wrote $Root\MonographPDF.exe (+ _internal\)"
Write-Host "OCR sidecars (required for offline OCR): engines\ocr + models\tessdata"
