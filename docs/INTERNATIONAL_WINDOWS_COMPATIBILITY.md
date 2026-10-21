# International Windows compatibility

Monograph PDF's interface and installer are in **English only**. They are designed to work on
Windows 10 and 11 in any display language and with any regional settings — English, Japanese,
Chinese, Korean, German, French and others — including user names, folder names and file names in
any script.

## Design rules

* **Unicode file APIs everywhere.** Python's file functions and `subprocess` use the Windows
  Unicode ("W") APIs; external programs (the OCR engine, Office, the update helper and Setup) are
  started with explicit argument lists, never through a shell command string. The update helper
  (C#) and Inno Setup are Unicode programs.
* **The OCR engine never sees a path.** Tesseract opens files with the Windows ANSI code page, so
  a folder name outside that code page (Japanese on an English system, accented letters on a
  Japanese system) used to make OCR fail. Monograph PDF now runs it in the folder that holds its
  language data (found by relative name), sends the page image through standard input and reads
  the result from standard output. This was found by the international test in CI (English Windows,
  code page 1252); the development computer uses the UTF-8 code page, which had hidden it.
* **No ASCII-only assumptions.** Paths are never re-encoded through the ANSI code page; JSON files
  the application writes for itself are UTF-8.
* **Locale-independent formats.** Versions are compared with ASCII digits only (Semantic
  Versioning), timestamps in signed manifests and records are ISO 8601 UTC
  (`2026-10-21T07:19:00Z`), signed metadata is canonical ASCII JSON, and no month or weekday names
  are parsed. Number and date formats of the regional settings affect only what is displayed.
* **Display language in problem reports** is the Windows UI language as a BCP 47 tag (`ja-JP`),
  so reports can be grouped by environment without any personal data.
* **Paths compared like Windows does**: installation folders are compared case-insensitively after
  normalization, so `D:\ソフトウェア\Monograph PDF\` and `d:\ソフトウェア\monograph pdf` are the
  same installation.

## What is tested

Automated tests that run on every platform the test suite runs on
(`tests/unit/test_international.py`, `test_update_staging.py`, `test_update_install.py`):

* opening and saving PDFs in Japanese, Chinese, Korean, German and French folders and file names,
  e.g. `C:\Users\田中太郎\Documents\研究資料.pdf`, `D:\研究データ\神経再生\実験結果.pdf`,
  `C:\Users\张伟\Documents\实验报告.pdf`, `C:\Users\김민수\Documents\연구자료.pdf` (as folders under a
  test directory);
* applying edits and writing the result to a Unicode path; images to PDF with Unicode names;
* a temporary folder under a Unicode user name (`…\Users\田中太郎\AppData\Local\Temp`);
* OCR of a scanned page in a Japanese-named folder with a Japanese-named temporary folder (needs the
  pinned OCR engine; skipped where it is not installed);
* Unicode arguments passed unchanged to a child process (the way the helper and Setup are started);
* update staging, cleanup, hand-off records and Setup's `/DIR=` argument under Japanese, Chinese,
  Korean and accented folder names; installation detection of Unicode installation folders;
* problem-report records under a Unicode profile;
* version comparison and signed-manifest verification while the process locale is Japanese, German,
  French, Turkish, Korean or Chinese (each skipped where that locale is not installed).

Windows end-to-end (`scripts/test_update_e2e.py`): a per-user installation into a folder named
`ソフトウェア` is upgraded through the real update helper and Setup.

## What these tests do not prove

They run on the test machine's own Windows installation (English display language, UTF-8 code page
— the Windows "Beta: Use Unicode UTF-8" setting) and in CI (English, code page 1252), with
Unicode **paths** and simulated process locales. They are **not** a verification on a real
Japanese, Chinese, Korean, German or French Windows installation, where the system code page,
default fonts, the user-profile path chosen by Windows, the Office installation and the input
methods differ. Before claiming support for a localized Windows edition, test there at least:
installation and upgrade, the first start, opening and saving, OCR with Japanese text, printing,
Office conversion, and the update and problem-report dialogs.

## Known limitations

* Office conversion depends on the locally installed Office or LibreOffice and its own language
  handling.
* Newly inserted text uses Windows' fonts; when a requested typeface is missing, the bundled Noto
  fallback fonts (including Noto Sans CJK JP) are used ([THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)).
  Chinese and Korean text then relies on the CJK fallback's coverage or on Windows' own fonts.
* The interface is English only; there is no translation.
