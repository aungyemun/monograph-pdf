# Component compatibility matrix (Option B audit)

Classification: **A** shared all · **B** shared two · **C** Windows · **D** Linux · **E** macOS ·
**F** platform replacement · **G** legacy · **H** uncertain / incomplete

| Component | Class | Notes | Key paths |
| :--- | :---: | :--- | :--- |
| PySide6 GUI / PDF edit / annotations | A | Shared core on all tips | `ui/`, `core/editing/`, `engines/` |
| PDF security / protection | A | Prefer main print-temp behaviour over macos deletions | `core/security/`, `core/printing/ops.py` |
| Preferences | A | Already XDG / AppData / Application Support | `core/user_prefs.py` |
| Runtime paths | B/F | `platform_paths` + `app/paths` | `core/platform_paths.py`, `app/paths.py` |
| Single-instance | F | Windows mutex; Unix `fcntl` | `app/single_instance.py` |
| OCR discovery | F | Non-`.exe` names on Unix | `core/ocr/paths.py`, `scripts/vendor_ocr*` |
| Fonts | C/E (+H Linux) | Windows registry and macOS font folders; Linux fontconfig still TODO | `core/editing/system_fonts.py` |
| Office conversion | A+C | COM Windows-only; LibreOffice PATH / Applications | `core/convert/office_bridge.py` |
| Printing | A | Qt print; platform temp cleanup | `core/printing/`, `ui/print_dialog.py` |
| Default PDF app | C+D | Windows Settings; Linux XDG (`linux_desktop`) | `ui/main_window.py`, `core/linux_desktop.py` |
| Updates | C | Windows Ed25519 + Releases API discovery | `core/updates/`, `resources/update/` |
| Packaging | C/D/E | Inno / `installer/linux` / macOS `.app` scripts | `installer/`, `scripts/build_*` |
| Versions | F | Independent lines | `versions/*.txt`, root `VERSION` (Windows mirror) |

Audit tips (pre-unification): `main` `4ef95e3`, `linux` `bc5fa581`, `macos` `0bae21d2`.
