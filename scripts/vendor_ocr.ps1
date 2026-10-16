# Packaging-time OCR vendor (NOT used by the app at runtime).
# Places Tesseract + eng/jpn/osd under engines/ocr and models/tessdata.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/vendor_ocr.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$OcrDir = Join-Path $Root "engines\ocr"
$Tessdata = Join-Path $Root "models\tessdata"
$ToolsCache = Join-Path $Root "tools\ocr_cache"
New-Item -ItemType Directory -Force -Path $OcrDir, $Tessdata, $ToolsCache | Out-Null

function Get-File($Url, $Dest) {
    if (Test-Path $Dest) {
        Write-Host "Exists: $Dest"
        return
    }
    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
}

# --- Language data (tessdata_fast, offline thereafter) ---
$LangBase = "https://github.com/tesseract-ocr/tessdata_fast/raw/main"
foreach ($lang in @("eng", "jpn", "osd")) {
    $dest = Join-Path $Tessdata "$lang.traineddata"
    Get-File "$LangBase/$lang.traineddata" $dest
}

# --- Tesseract Windows binary (portable zip if available; else copy from PATH) ---
$TessExe = Join-Path $OcrDir "tesseract.exe"
if (-not (Test-Path $TessExe)) {
    $existing = Get-Command tesseract -ErrorAction SilentlyContinue
    if ($existing) {
        Copy-Item $existing.Source $TessExe -Force
        $bindir = Split-Path $existing.Source
        Get-ChildItem $bindir -Filter "*.dll" | Copy-Item -Destination $OcrDir -Force
        Write-Host "Copied system tesseract to engines/ocr"
    } else {
        # Official-ish portable build hosted by UB Mannheim mirrors as zip is uncommon;
        # fall back to winget/choco silent if present.
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if ($winget) {
            Write-Host "Attempting winget install of Tesseract OCR (packaging machine only)..."
            winget install --id UB-Mannheim.TesseractOCR -e --accept-package-agreements --accept-source-agreements | Out-Host
            $guess = @(
                "$env:LOCALAPPDATA\Programs\Tesseract-OCR\tesseract.exe",
                "C:\Program Files\Tesseract-OCR\tesseract.exe"
            ) | Where-Object { Test-Path $_ } | Select-Object -First 1
            if ($guess) {
                Copy-Item $guess $TessExe -Force
                $bindir = Split-Path $guess
                Get-ChildItem $bindir -Filter "*.dll" | Copy-Item -Destination $OcrDir -Force
                # Prefer project tessdata; also copy if empty
                $sysTess = Join-Path $bindir "tessdata"
                if (Test-Path $sysTess) {
                    foreach ($lang in @("eng", "jpn", "osd")) {
                        $src = Join-Path $sysTess "$lang.traineddata"
                        $dst = Join-Path $Tessdata "$lang.traineddata"
                        if ((Test-Path $src) -and -not (Test-Path $dst)) {
                            Copy-Item $src $dst -Force
                        }
                    }
                }
            }
        }
    }
}

# Manifest for audits
$manifest = @{
    vendored_at = (Get-Date).ToString("o")
    tesseract   = (Test-Path $TessExe)
    tessdata    = @{}
}
foreach ($lang in @("eng", "jpn", "osd")) {
    $manifest.tessdata[$lang] = Test-Path (Join-Path $Tessdata "$lang.traineddata")
}
$manifest | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $OcrDir "MANIFEST.json")
Write-Host "OCR vendor complete. tesseract=$($manifest.tesseract)"
$manifest.tessdata.GetEnumerator() | ForEach-Object { Write-Host ("  {0}={1}" -f $_.Key, $_.Value) }
