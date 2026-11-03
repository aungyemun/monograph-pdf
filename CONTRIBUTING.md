# Contributing

Thank you for helping improve Monograph PDF. It is maintained by one person, so small, focused
changes with a clear description and tests are the easiest to review.

## Reporting problems and suggesting features

* Use the [issue templates](https://github.com/aungyemun/monograph-pdf/issues/new/choose). For a
  bug, give the platform and version, the steps to reproduce it and what you expected.
* **Never attach confidential or personal documents.** Use a small sample file, and remove personal
  folder names from logs and screenshots.
* Report security vulnerabilities privately; see the [Security policy](SECURITY.md).

## Code changes

1. For anything larger than a small fix, open an issue first to discuss it.
2. Branch from the latest **`main`** with a short-lived name: `feature/windows-*`, `feature/linux-*`,
   `feature/macos-*`, `fix/*`, `security/*` or `integration/*`. See
   [Cross-platform development](docs/CROSS_PLATFORM_DEVELOPMENT.md).
3. Set up the environment and run the tests ([Build and Runtime](docs/BUILD_AND_RUNTIME.md),
   [Testing](docs/TESTING.md)):

   ```powershell
   # Windows
   powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
   powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1
   ```

   ```bash
   # Linux and macOS
   bash scripts/setup_env.sh
   bash scripts/run_tests.sh
   ```

4. Add or update tests for new behavior. Do not weaken existing tests.
5. Use only synthetic test documents; never add real documents to the repository.
6. Commit under your own name. Do not add `Co-authored-by` trailers or "Generated with …" lines for
   AI assistants (Claude, Cursor, Copilot and similar); human co-authors are welcome. The
   *Commit message check* workflow rejects them; install the same check locally with
   `cp scripts/ci/commit-msg .git/hooks/commit-msg`.
7. Do not bump versions for documentation or layout changes. For an approved release, bump only
   that platform's `versions/<platform>.txt` (Windows also mirrors it into root `VERSION`).

`main` accepts a pull request only after the Windows, Linux and macOS tests pass. In the pull
request, list skipped tests and any native checks you could not run (install/upgrade, printing,
Office, OCR). Keep shared PDF behavior in shared code; see the
[repository layout](docs/REPOSITORY_LAYOUT.md).

## Project principles

* **Offline-first:** documents are processed locally. No telemetry, analytics or uploads. Network
  use is limited to the existing update checks and OCR-language downloads, which need user consent,
  HTTPS and integrity checks; automatic update checks stay off by default.
* **Licensing:** new dependencies need a license compatible with AGPL-3.0-or-later and must be added
  to [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the
  [dependency inventory](licenses/DEPENDENCY_INVENTORY.md).

## License of contributions

By submitting a contribution, you confirm that you have the right to contribute it and agree to
license it under the [GNU Affero General Public License, version 3 or later](LICENSE)
(AGPL-3.0-or-later), the license of Monograph PDF.

© 2026 Aung Ye Mun
