# Cross-platform development (Option B)

Monograph PDF uses **one protected `main` branch** with shared application code and
**independent Windows, Linux and macOS implementations**, versions and release schedules.

## Architecture

| Area | Location | Notes |
| :--- | :--- | :--- |
| Shared GUI / PDF core | `app/`, `core/`, `ui/`, `engines/` | Same product features on every OS |
| Platform helpers | `core/platform_paths.py`, `app/single_instance.py`, `core/ocr/paths.py`, `core/linux_desktop.py`, `platforms/` | Selected by `sys.platform` |
| Platform versions | `versions/windows.txt`, `versions/linux.txt`, `versions/macos.txt` | Independent SemVer lines |
| Windows packaging | `installer/*.iss`, `scripts/build_*.ps1`, `scripts/signing/` | Inno Setup; signed update manifests |
| Linux packaging | `installer/linux/`, `scripts/setup_env.sh`, `scripts/vendor_ocr.sh` | Per-user install; no auto-updates yet |
| macOS packaging | (integration branch / `macos` tip) `scripts/build_app.sh`, `package_macos.sh` | `.app` / dmg / pkg — land via macOS PR |

Root `VERSION` **mirrors the Windows line** so existing Windows build tools keep working.
Runtime code must use `core.versioning.get_version()` (host OS) or
`get_version("linux")` / `get_version("macos")` / `get_version("windows")`.

## Branching policy

Permanent integration branch: **`main`** only.

Temporary branches (from latest approved `main`):

* `feature/windows-*`, `feature/linux-*`, `feature/macos-*`
* `fix/windows-*`, `fix/linux-*`, `fix/macos-*`
* `security/*`, `integration/*`, `release/*`

Platform-long-lived branches (`linux`, `macos`) are **legacy sources** until their unique work
is merged through reviewed PRs and verified on the native computers. Do not treat them as the
source of truth after Option B migration completes.

## Three-computer workflow

Each developer machine keeps its own clone.

```bash
# Daily sync (never discard local work)
git status -sb
git fetch origin
git switch main
git pull --ff-only origin main

# New work
git switch -c feature/linux-short-name
# … edit, test natively …
git push -u origin HEAD
# open a PR targeting main
```

Windows: run `scripts/setup_env.ps1`, `scripts/run_tests.ps1`, Inno builds.  
Linux: `bash scripts/setup_env.sh`, `bash scripts/run_tests.sh`, `installer/linux/install.sh`.  
macOS: use the macOS scripts once they are on `main` (see macOS integration PR).

## CI

| Workflow | Job name | Runner |
| :--- | :--- | :--- |
| `windows-ci.yml` | Tests (Windows, Python 3.11) | `windows-2022` |
| `linux-ci.yml` | Tests (Linux, Python 3.11) | `ubuntu-22.04` |
| `macos-ci.yml` | Tests (macOS, Python 3.11) | `macos-14` |

All three run on PRs to `main` and on pushes to `main`. They never publish releases and never
hold production signing keys. Skipped tests stay **SKIPPED** / **NOT VERIFIED**.

## Releases

Independent tags and schedules. Examples:

* Windows: `v0.5.0`, `v0.5.1` …
* Linux: prefer `v0.1.0-linux` when publishing (none published yet)
* macOS: published `v0.1.0-macos-1`

GitHub **Latest** is not a platform update channel. Windows clients use the hardened Releases API
discovery and Ed25519 key `27c3b3b23b949c40` (730-day manifests). Linux/macOS automatic updates
are **not** claimed until implemented and tested on those platforms.

## Recovery before migration

See backup branches `backup/pre-unification-2026-10-25/*` and annotated tags
`backup-pre-unification-2026-10-25-*`, plus the offline Git bundle under the maintainer’s
`MonographPDF-recovery/` folder (outside the repository).
