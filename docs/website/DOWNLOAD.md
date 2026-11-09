# Download and install

Monograph PDF is free. Download it **only** from the project's GitHub Releases page:
<https://github.com/aungyemun/monograph-pdf/releases>. Copies from other websites, file-sharing
services or e-mail attachments are not official, even if they carry the name Monograph PDF.

## Windows 10 and 11 (64-bit)

### 1. Download

Open the Releases page and choose the newest release whose name starts with **v** followed only by
numbers (for example `v0.5.1`). Releases ending in `-linux` or `-macos` are for other systems. Do not
rely on GitHub's "Latest" badge, because it may point to a macOS or Linux release.

Under **Assets**, download `MonographPDF_<version>_Setup.exe`.

### 2. Check that the file is genuine

The release notes list a long code for each file, called a **SHA-256 checksum**. If your download
gives the same code, it is exactly the file the release page lists.

1. Open the folder with the download, click the address bar, type `powershell` and press Enter.
2. Type the following line (with the version you downloaded) and press Enter:

   ```powershell
   Get-FileHash .\MonographPDF_<version>_Setup.exe -Algorithm SHA256
   ```

3. Compare the code shown with the one in the release notes. They must be identical. If they are
   not, delete the file and do not run it.

### 3. Install

Run the Setup file.

**"Windows protected your PC".** Monograph PDF does not have a paid code-signing certificate yet,
so Windows SmartScreen may show this warning for a new download. If you downloaded the file from
the official Releases page **and** the checksum matched, click **More info ▸ Run anyway**.
Otherwise, do not continue.

Choose **Only for me** (no administrator rights needed) or **For all users**. Setup can add
Monograph PDF to the *Open with* menu for PDF files. It never makes itself your default PDF program on its own
(you can choose that later in **Help** or in Windows).

Everything the program needs is included, so installing works without an internet connection.

### Requirements

| | Minimum | Recommended |
| :--- | :--- | :--- |
| Windows | Windows 10, 64-bit | Windows 11, 64-bit |
| Memory | 4 GB | 8 GB or more |
| Free disk space | 1 GB | 2 GB |
| Screen | 1280 × 720 | 1920 × 1080 or larger |
| Office | — | Microsoft Office or LibreOffice, only to turn Office files into PDFs |

### Updating

From version 0.5.0, **Help ▸ Check for Updates…** can download and install a new version for you
when you click **Update Now**. It accepts only updates signed by the project. Automatic checks are
off unless you switch them on. Older versions are updated by installing the new Setup file over
them; your settings are kept.

### Uninstalling

**Settings ▸ Apps ▸ Installed apps ▸ Monograph PDF ▸ Uninstall.** You are asked whether to remove
your Monograph PDF settings as well. Your own PDF documents are never removed.

## macOS and Linux

macOS (13 or later, Apple silicon) and Linux (x86_64) have their own releases, named `…-macos` and
`…-linux` on the Releases page. Instructions: [installation guide](../../INSTALLATION.md).

## More detail

* [Verifying an official download](../OFFICIAL_DOWNLOAD_VERIFICATION.md), including how to check
  the source code a release was built from
* [Installation guide](../../INSTALLATION.md) for silent installation, file types and troubleshooting
* [Code signing policy](../CODE_SIGNING_POLICY.md)
