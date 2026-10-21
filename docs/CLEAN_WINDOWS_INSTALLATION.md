# Clean Windows installation

## What a clean installation needs

Setup.exe installs Monograph PDF on Windows 10 1809+ or Windows 11 (x64) **without internet access** and without any other software. Nothing is downloaded during installation or at first start: no Python, no Visual C++ Redistributable, no .NET download, no OCR engine or language data, and no PATH change. See [WINDOWS_RUNTIME_DEPENDENCIES.md](WINDOWS_RUNTIME_DEPENDENCIES.md) and [PREREQUISITE_MANAGEMENT.md](PREREQUISITE_MANAGEMENT.md).

Installation modes:

| Mode | Folder | Elevation |
|---|---|---|
| For all users (default when run as administrator) | `C:\Program Files\Monograph PDF` | a normal UAC prompt |
| For the current user | `%LOCALAPPDATA%\Programs\Monograph PDF` | none |

Custom and Unicode folders are supported in both modes. Microsoft Office or LibreOffice is needed only for Word, Excel and PowerPoint to PDF; everything else works without them.

## What has been verified, and where

| Check | Environment | Result |
|---|---|---|
| Installer test (`scripts/test_installer.ps1`): per-user install, registrations, shortcuts, self-check, launch, User Guide, uninstall while running, complete uninstall with a locked file, reinstall, upgrade matrix, PDF Editor 0.1.5 migration matrix | development PC, Windows 11 Pro 25H2 (build 26200), en-US, standard (non-elevated) account; 0.3.0 development build 96b6c6f | 262 passed, 0 failed, 1 skipped (the all-users PDF Editor case needs an elevated shell) |
| Program loads its own VC++ runtime, not the system's | same PC (system-wide VC++ 14.51 present) | verified with a loaded-module listing |
| No network use in normal PDF work, OCR and the self-check | same PC, connection monitoring of the whole process tree | see the network audit in the release notes |
| Live use of the installed build (open a PDF with a Japanese file name, edit, compress to a target size, PDF to PowerPoint with mixed page sizes, print to Microsoft Print to PDF in black and white, 4 pages per sheet) | same PC, test installation in a separate folder with separate settings | worked. One defect was found and fixed: File ▸ Save a Copy ▸ Whole Document raised an error from the menu. |

## Not verified: a clean PC

These checks ran on a development PC, not on a clean Windows installation. That PC has Python, Visual Studio runtimes, Microsoft 365, Git and other tools installed. The dependency evidence (import tables, loaded modules, `--check`) shows that the program does not rely on them. Still, **installation on a clean Windows has not been verified**, and is reported as BLOCKED until it is done.

The following are also not verified:

- Japanese, Chinese, Korean, German or French Windows (the Unicode tests are simulated on an English Windows with Unicode folder and file names);
- Windows 10;
- an administrator-run all-users installation of 0.3.0.

### How to run the clean-PC test

Windows Sandbox (Windows 11 Pro or Enterprise) is a disposable clean Windows. To enable it:

1. Open **Turn Windows features on or off**.
2. Tick **Windows Sandbox**.
3. Restart.

Then in the Sandbox:

1. Copy `MonographPDF_<version>_Setup.exe` in, with networking disabled (a `.wsb` file with `<Networking>Disable</Networking>`).
2. Install for all users (UAC) and for the current user.
3. Open, edit, save and reopen a PDF.
4. Run OCR (English and Japanese).
5. Convert to Word and PowerPoint.
6. Compress and print to Microsoft Print to PDF.
7. Confirm there are no missing-DLL messages.
8. Uninstall.

A Japanese-display-language test needs a Japanese language pack inside the VM, or a Japanese Windows VM.
