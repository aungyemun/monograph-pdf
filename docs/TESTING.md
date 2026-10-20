# Testing

## Layout

| Path | Purpose |
|---|---|
| `tests/unit/` | Fast pure tests |
| `tests/integration/` | Cross-module checks |
| `tests/ui/` | Qt UI (pytest-qt) |
| `tests/fixtures/` · `tests/samples/` | Fixtures / samples |
| `tests/outputs/` | All generated artifacts |

Never leave temp PDFs, screenshots, or logs in the repo root.

## Running

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1
# or: .\env\Scripts\python.exe -m pytest
```

`pytest.ini`: `pythonpath = .`, `qt_api = pyside6`.

## Coverage focus

* Viewer, text edit / undo, forms, tables, layout, OCR
* Organize, convert/export; **Office→PDF supported when Microsoft Office or LibreOffice is installed locally**
* Security, redaction, annotations, print
* Highlight Round 7: toggle, mid-stroke Esc, color switch, eraser, preservation across edits (`tests/ui/test_highlight_round7.py`, `test_highlight_continuous.py`)
* Docs / menus: User Guide menu paths match the app (`test_user_guide_menus.py`)
* Menu audit (`test_menu_audit_fixes.py`); deep harness `scripts\deep_ui_audit.py` (manual)
* Page design: header/footer slots, watermark and background placement on 0/90/180/270° and cropped pages (measured on renders), replace/remove, shared fonts/pictures (`tests/integration/test_page_marks.py`, `tests/ui/test_page_marks_ui.py`)
* Redaction beyond page content: fields/comments/links under marks, whole pages, residue report and removal, checked in raw bytes (`tests/integration/test_redaction_residue.py`, `tests/ui/test_redaction_ui.py`)
* Merge outlines and protected inputs; Images to PDF without photo metadata (`test_merge_outline_and_protection.py`, `test_images_to_pdf_privacy.py`)
* Menus and toolbars: one Alt-letter per menu item, no duplicate shortcuts, icon + tooltip on every command, toolbar commands present in menus (`tests/ui/test_menu_toolbar_inventory.py`); full JSON inventory of every menu item, toolbar control and shortcut: `scripts\audit\ui_control_inventory.py out.json`
* Bookmarks (add / rename / move / retarget / delete, undo, save, web-link bookmarks kept), Remove Hidden Information (checked in every decompressed object of the output), Bates numbers, print odd/even/reverse/without comments, password strength (`test_bookmark_ops.py`, `test_remove_hidden_info.py`, `test_bates_and_print_options.py`, `test_password_strength.py`, `tests/ui/test_acrobat_style_tools_ui.py`)
* Installer: `scripts\test_installer.ps1`
* Audit tools (`scripts\audit\`): installed-copy file/registry audit, isolated run of an installed copy (modules, sockets, profile writes), generated inputs and an independent verifier for real-GUI sessions, timing of page design / redaction / merge / Images to PDF
* Maintainer-local real-PDF scripts (gitignored) when present

## Installer and uninstaller test

`scripts\test_installer.ps1` installs Setup, launches the app, checks registrations/shortcuts/self-check, uninstall/reinstall, upgrade and internal-compatibility matrices. Logs under `build\installer-test\`.

## Security tests

`tests/unit/test_security_hardening.py`, `tests/ui/test_security_ui.py` — safe paths, full-path process starts, no network, encryption preserved on Save As.

## Related

[BUILD_AND_RUNTIME.md](BUILD_AND_RUNTIME.md) · [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md)
