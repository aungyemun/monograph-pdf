# Prepare the OCR engine for a release build (packaging machine only; never used by the app at run time).
#
# Places Tesseract 5.4.0.20240606 (Windows x64) in engines\ocr and the tessdata_fast eng / jpn / osd
# language data in models\tessdata, ONLY if every file is SHA-256 identical to the engine Monograph PDF
# ships (scripts\ci\ocr_engine_pins.json). Anything else is refused and nothing is changed.
#
# 1. Install exactly that Tesseract version from the approved Chocolatey package (also used by CI):
#        choco install tesseract --version 5.4.0.20240606 -y
# 2. powershell -ExecutionPolicy Bypass -File scripts\vendor_ocr.ps1 [-From "C:\Program Files\Tesseract-OCR"]
#
# The language data is downloaded from the tessdata_fast release tag 4.1.0 and checked against the pins.
# This script itself downloads no program files and never picks a newer Tesseract. The work is done by
# scripts\ci\stage_ocr_engine.py; afterwards the result is verified again with --verify.
# (Before 0.2.4 this script installed the newest Tesseract through winget and downloaded the language
# data from a moving branch without any hash check; that route is retired.)

param(
    [string]$From = (Join-Path $env:ProgramFiles "Tesseract-OCR")
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Py = Join-Path $Root "env\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Missing .\env. Run scripts\setup_env.ps1 first." }
$Stager = Join-Path $Root "scripts\ci\stage_ocr_engine.py"

& $Py $Stager --from $From --require
if ($LASTEXITCODE -ne 0) {
    throw "OCR engine not prepared: the installed Tesseract at '$From' or the downloaded language data does not match the pinned release copy (see above)."
}
& $Py $Stager --verify
if ($LASTEXITCODE -ne 0) { throw "OCR engine verification failed (see above)." }
Write-Host "OCR engine ready in engines\ocr and models\tessdata (pinned and verified)."
