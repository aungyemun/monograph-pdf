# Build canonical ./MonographPDF.exe via PyInstaller into project root.
# Uses --onedir (exe + _internal/) for fast cold start — avoids onefile temp extraction.
# Intermediates: ./build  Distributable also under ./dist/MonographPDF/
# Usage: powershell -ExecutionPolicy Bypass -File scripts/build_exe.ps1 [-UpdateConfig <folder>]
#   -UpdateConfig: TEST BUILDS ONLY. Replaces the bundled resources\update (update_config.json and an
#   optional test CA) with the files in <folder>, for update tests against a local mock server with
#   synthetic keys. Release builds (scripts\build_release.ps1) never pass it, and verify_release.py
#   fails if the bundled configuration differs from the repository's.
param([string]$UpdateConfig = "")

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Py = Join-Path $Root "env\Scripts\python.exe"

# Controlled build PATH: PyInstaller's Qt hook copies OpenSSL DLLs it finds on PATH into the bundle. Drop every
# PATH folder outside Windows and the project that holds one (typically Git for Windows' mingw64\bin) so the
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

# Remove bundled parts Monograph PDF never uses (Qt's network/TLS plugins, Qt Quick/QML, Qt's PDF plugin,
# FFmpeg video I/O, software OpenGL); fails if a remaining DLL still needs one. Python's ssl module stays
# for update checks and approved problem reports.
& $Py "$Root\scripts\packaging\check_release.py" prune $OutDir
if ($LASTEXITCODE -ne 0) { Write-Error "Pruning the bundle failed (see above)." }
# Build provenance inside the program: the commit it was built from (shown in About; checked by
# verify_release.py against the source archive). A build from an export without .git can pass the commit
# in MONOGRAPH_PDF_BUILD_COMMIT.
$Commit = $env:MONOGRAPH_PDF_BUILD_COMMIT
$Dirty = $false
if (-not $Commit) {
    $Commit = (& git -C $Root rev-parse HEAD 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $Commit) { $Commit = "unknown" }
    else { $Dirty = [bool](& git -C $Root status --porcelain --untracked-files=no 2>$null) }
}
$BuildInfoJson = @{ schema = 1; commit = "$Commit".Trim(); dirty = $Dirty; version = $Version } | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText((Join-Path $OutInternal "resources\build_info.json"), $BuildInfoJson, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Build provenance: commit $Commit$(if ($Dirty) { ' (uncommitted changes!)' })"
# Reproducible launcher: PyInstaller stamps the build time into MonographPDF.exe's PE headers; use the
# commit time instead (SOURCE_DATE_EPOCH if set, for builds from an export without .git).
$Epoch = $env:SOURCE_DATE_EPOCH
if (-not $Epoch) {
    $Epoch = (& git -C $Root log -1 --format=%ct 2>$null)
    if ($LASTEXITCODE -ne 0) { $Epoch = $null }
}
if ($Epoch) {
    & $Py "$Root\scripts\packaging\normalize_pe.py" --epoch "$Epoch".Trim() $OutExe
    if ($LASTEXITCODE -ne 0) { Write-Error "Normalizing the launcher's time stamps failed." }
} else {
    Write-Warning "No commit time (no .git, no SOURCE_DATE_EPOCH): MonographPDF.exe keeps PyInstaller's build-time stamp."
}
if ($UpdateConfig) {
    $Bundled = Join-Path $OutInternal "resources\update"
    Write-Warning "TEST BUILD: replacing the bundled update configuration with $UpdateConfig"
    Remove-Item -Recurse -Force $Bundled
    New-Item -ItemType Directory -Force $Bundled | Out-Null
    Copy-Item (Join-Path $UpdateConfig "*") $Bundled -Force
}

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
