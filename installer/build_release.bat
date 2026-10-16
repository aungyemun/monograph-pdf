@echo off
rem Monograph PDF - one-step release build.
rem Runs tests, builds MonographPDF.exe, runs its self-test, compiles Setup.exe with Inno Setup,
rem and packages installer\release\ + installer\MonographPDF_<version>_Installer.zip + installer\build_release_summary.txt.
rem Options are passed through: -SkipTests  -SkipExe

setlocal
set "ROOT=%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\build_release.ps1" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo Release build FAILED with exit code %RC%.
) else (
    echo.
    echo Release build finished. Outputs are in "%~dp0".
)
rem MONOGRAPH_PDF_NO_PAUSE=1 skips the pause (PDFEDITOR_NO_PAUSE is a deprecated alias)
if "%MONOGRAPH_PDF_NO_PAUSE%"=="" if /I "%PDFEDITOR_NO_PAUSE%"=="1" set "MONOGRAPH_PDF_NO_PAUSE=1"
if /I not "%MONOGRAPH_PDF_NO_PAUSE%"=="1" pause
exit /b %RC%
