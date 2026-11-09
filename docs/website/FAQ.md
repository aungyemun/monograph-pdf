# Frequently asked questions

### Is Monograph PDF really free?

Yes. There is no price, no subscription, no trial period and no advertising. The program is open
source under the GNU Affero General Public License (AGPL-3.0-or-later).

### Do my documents leave my computer?

No. Documents are opened, edited and saved only on your computer. Monograph PDF connects to the
internet only to check for updates when you ask (automatic checks are off at first) and to
download an extra text-recognition language when you click **Download and Install**. See
[Privacy](PRIVACY.md).

### Do I need an internet connection?

No. Installing and all editing, converting and text recognition work offline. You need a
connection only to download the program, check for updates or add more recognition languages.

### Why does Windows say "Windows protected your PC"?

Monograph PDF is not yet signed with a paid code-signing certificate, so Windows SmartScreen warns
about it. Download it only from the official
[Releases page](https://github.com/aungyemun/monograph-pdf/releases), check its SHA-256 checksum
([how](DOWNLOAD.md#2-check-that-the-file-is-genuine)) and only then choose
**More info ▸ Run anyway**.

### Which systems does it run on?

Windows 10 and 11 (64-bit) is the main version. There are also versions for macOS 13 or later on
Apple silicon and for Linux (x86_64). Each system has its own version numbers; the Releases page
lists the current one for each. Windows on ARM, Intel Macs, phones and tablets have not been
tested.

### Can I copy text from a PDF?

Yes, with **Select Text** (Windows version 0.6.0 and later): drag over the text and press `Ctrl+C`.
Scanned pages contain only a picture of the text, so recognise the text first with **OCR**.

### Can it read scanned documents?

Yes. Text recognition (OCR) is built in for English and Japanese and works offline. On Windows,
45 more languages can be added from the **OCR** menu.

### Can I sign a PDF?

You can add a visual signature, typed, drawn or from a picture. Certificate-based digital
signatures (the kind that prove who signed and that nothing changed afterwards) are not supported.

### Is blacking out text enough to hide it?

No. A black box drawn over text leaves the text in the file, where it can be copied. Use
**Redaction**, which deletes the marked text from the file, and check the result before you share
it.

### Can it convert PDF to Word?

Yes, to Word, Excel and PowerPoint. Simple documents convert well; complex layouts may need some
tidying afterwards. Converting Office files into PDFs needs Microsoft Office or LibreOffice on
your computer.

### Will opening a PDF change it?

No. A PDF changes only when you save it. Commands such as adding page numbers or protecting with a
password save a new file and leave the open document as it is.

### What happens to my settings when I update or uninstall?

Updating keeps your settings. When you uninstall on Windows, you are asked whether to remove them.
Your documents are never removed.

### How do I report a problem or suggest something?

Use the [issue templates on GitHub](https://github.com/aungyemun/monograph-pdf/issues/new/choose).
Never attach confidential or personal documents; use a small sample file instead. Report security
problems privately as described in the [security policy](../../SECURITY.md).

### Who makes Monograph PDF?

Aung Ye Mun develops it as an open-source project. Contributions are welcome; see
[Contributing](../../CONTRIBUTING.md).
