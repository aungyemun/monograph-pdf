# Prepare self-contained Windows development release.
# 1) Offline feature smoke
# 2) Version bump (only after smoke passes)
# 3) Build MonographPDF.exe into dist/ + root
# 4) Runtime manifest + PE metadata verification
# 5) Clean stale root executables
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts/prepare_windows_release.ps1
#        powershell -ExecutionPolicy Bypass -File scripts/prepare_windows_release.ps1 -SkipBump

param(
    [switch]$SkipBump
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Py = Join-Path $Root "env\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Error "Missing ./env. Run scripts/setup_env.ps1 first."
}

$LogDir = Join-Path $Root "tests\outputs\logs"
New-Item -ItemType Directory -Force -Path $LogDir, (Join-Path $Root "dist") | Out-Null
$Log = Join-Path $LogDir ("release-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")

function Write-Log([string]$Message) {
    $line = "$(Get-Date -Format o) $Message"
    Write-Host $Message
    Add-Content -Path $Log -Value $line
}

Write-Log "=== Monograph PDF Windows release prepare ==="
Write-Log "Log: $Log"

# --- Offline smoke (blocks proxy to discourage network) ---
Write-Log "Running offline release smoke..."
$env:QT_QPA_PLATFORM = "offscreen"
$env:NO_PROXY = "*"
$env:HTTP_PROXY = "http://127.0.0.1:9"
$env:HTTPS_PROXY = "http://127.0.0.1:9"
& $Py "$Root\scripts\validate_release_smoke.py" 2>&1 | Tee-Object -FilePath $Log -Append
if ($LASTEXITCODE -ne 0) {
    Write-Error "Release smoke failed — version not bumped, exe not rebuilt."
}

# --- Unit/UI branding gates ---
Write-Log "Running branding + product meta tests..."
& $Py -m pytest tests/unit/test_product_meta.py tests/ui/test_branding_ui.py tests/unit/test_versioning.py -q --tb=line 2>&1 | Tee-Object -FilePath $Log -Append
if ($LASTEXITCODE -ne 0) {
    Write-Error "Gate tests failed — aborting release."
}

# --- Version bump (policy: only after successful checks) ---
if (-not $SkipBump) {
    Write-Log "Bumping VERSION..."
    & $Py "$Root\scripts\bump_version.py" 2>&1 | Tee-Object -FilePath $Log -Append
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Log "SkipBump set — keeping current VERSION"
}

$Version = (& $Py "$Root\scripts\read_version.py").Trim()
Write-Log "Release version: $Version"

# --- Build ---
Write-Log "Building MonographPDF.exe..."
& powershell -ExecutionPolicy Bypass -File "$Root\scripts\build_exe.ps1" 2>&1 | Tee-Object -FilePath $Log -Append
if ($LASTEXITCODE -ne 0) {
    Write-Error "Build failed."
}

# --- Clean root: only MonographPDF.exe may remain as app executable ---
Get-ChildItem -Path $Root -Filter "*.exe" -File | ForEach-Object {
    if ($_.Name -ne "MonographPDF.exe") {
        Write-Log "Removing stale root executable: $($_.Name)"
        Remove-Item -Force $_.FullName
    }
}

$Exe = Join-Path $Root "MonographPDF.exe"
$DistDir = Join-Path $Root "dist\MonographPDF"
$DistExe = Join-Path $DistDir "MonographPDF.exe"
$DistInternal = Join-Path $DistDir "_internal"
$RootInternal = Join-Path $Root "_internal"
if (-not (Test-Path $Exe)) { Write-Error "Missing root MonographPDF.exe" }
if (-not (Test-Path $DistExe)) { Write-Error "Missing dist/MonographPDF/MonographPDF.exe" }
if (-not (Test-Path $DistInternal)) { Write-Error "Missing dist/MonographPDF/_internal" }
if (-not (Test-Path $RootInternal)) { Write-Error "Missing root _internal (onedir payload)" }

# --- Sidecar structure for OCR (must sit beside exe) ---
$Tess = Join-Path $Root "engines\ocr"
$Data = Join-Path $Root "models\tessdata"
if (-not (Test-Path $Tess)) { Write-Error "Missing engines/ocr beside executable" }
if (-not (Test-Path $Data)) { Write-Error "Missing models/tessdata beside executable" }

# --- PE metadata ---
$vi = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($Exe)
Write-Log "PE ProductName: $($vi.ProductName)"
Write-Log "PE FileDescription: $($vi.FileDescription)"
Write-Log "PE OriginalFilename: $($vi.OriginalFilename)"
Write-Log "PE InternalName: $($vi.InternalName)"
Write-Log "PE ProductVersion: $($vi.ProductVersion)"
Write-Log "PE FileVersion: $($vi.FileVersion)"
Write-Log "PE LegalCopyright: $($vi.LegalCopyright)"

if ($vi.ProductName -ne "Monograph PDF") {
    Write-Error "ProductName metadata mismatch: '$($vi.ProductName)'"
}
if ($vi.FileDescription -ne "Monograph PDF") {
    Write-Error "FileDescription metadata mismatch: '$($vi.FileDescription)'"
}
if ($vi.OriginalFilename -and ($vi.OriginalFilename -ne "MonographPDF.exe")) {
    Write-Error "OriginalFilename metadata mismatch: '$($vi.OriginalFilename)'"
}
# ProductVersion from VERSION file (may be "0.0.9" or "0.0.9.0")
if ($vi.ProductVersion -notmatch [regex]::Escape($Version)) {
    Write-Error "ProductVersion '$($vi.ProductVersion)' does not contain VERSION $Version"
}

# --- Manifest ---
Write-Log "Writing runtime manifest..."
& $Py "$Root\scripts\write_runtime_manifest.py" 2>&1 | Tee-Object -FilePath $Log -Append
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Stage versioned copy under dist/ (full onedir: exe + _internal)
$StageDir = Join-Path $Root "dist\MonographPDF-$Version-windows-x64"
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null
Copy-Item -Force $DistExe (Join-Path $StageDir "MonographPDF.exe")
if (Test-Path (Join-Path $StageDir "_internal")) {
    Remove-Item -Recurse -Force (Join-Path $StageDir "_internal")
}
Copy-Item -Recurse -Force $DistInternal (Join-Path $StageDir "_internal")
Copy-Item -Force (Join-Path $Root "dist\runtime_manifest.json") (Join-Path $StageDir "runtime_manifest.json")
# Note: OCR sidecars remain at install/project root relative layout (engines/, models/)
Write-Log "Staged: $StageDir"

# --- Windowed build: no console subsystem ---
# PyInstaller --windowed sets WINDOWS subsystem; verify via optional dump if available.
Write-Log "Release prepare complete: $Exe (version $Version)"
Write-Log "Canonical launch: ./MonographPDF.exe"
exit 0
