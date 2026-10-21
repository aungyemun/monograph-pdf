# Contributing

Thank you for your interest in contributing to Monograph PDF. The project is independently
maintained, so focused changes with clear explanations and relevant tests are appreciated.

## Reporting problems and suggesting features

* Use the [issue templates](https://github.com/aungyemun/monograph-pdf/issues/new/choose) for bugs
  and feature requests. For a bug, give the version, the exact steps to reproduce it, and what you
  expected to happen.
* **Never attach confidential or personal documents.** Create a small sample file instead, and remove
  personal folder names from logs and screenshots.
* Report security vulnerabilities privately, as described in the [Security policy](SECURITY.md).

## Code changes

1. For anything larger than a small fix, open an issue first so the change can be discussed.
2. Set up the development environment and run the application and tests as described in
   [Build and Runtime](docs/BUILD_AND_RUNTIME.md) and [Testing](docs/TESTING.md):

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
   powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1
   ```

3. Keep changes small and add or update tests for new behavior. Do not weaken existing tests.
4. Use only synthetic test documents; do not add real documents to the repository.

## Project principles

* **Offline only:** no network access, telemetry, analytics or online services.
* **Privacy:** documents are processed only on the user's computer; nothing is collected.
* **Licensing:** new dependencies must have a license compatible with AGPL-3.0-or-later and must be
  added to [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the
  [dependency inventory](licenses/DEPENDENCY_INVENTORY.md).

## License of contributions

By submitting a contribution, you confirm that you have the right to contribute the material and
agree to license your contribution under the
[GNU Affero General Public License, version 3 or later](LICENSE) (AGPL-3.0-or-later), the license of
Monograph PDF.
