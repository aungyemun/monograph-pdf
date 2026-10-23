# Secure updates

Status: **included since 0.3.0; switched on from 0.4.1** with the production update-signing key
(key id `27c3b3b23b949c40`). 0.3.0 and 0.4.0 ship with updates switched off and no trusted key, so
they cannot update themselves: users install 0.4.1 once with Setup from the
[GitHub Releases page](https://github.com/aungyemun/monograph-pdf/releases); the first upgrade through
the updater is from 0.4.1 to a later release.

Validation status: the signing key, the manifest checks and the user interface are tested (see
[Testing](#testing)). The packaged 0.4.1 build has **not yet** passed the end-to-end update test
(`scripts/test_update_e2e.py`) or the 0.4.0 → 0.4.1 Setup upgrade test on a disposable Windows
installation; 0.4.1 is not published before both pass.

Related: [AUTOMATIC_UPGRADE_AND_CLEANUP.md](AUTOMATIC_UPGRADE_AND_CLEANUP.md) (what happens after
**Update Now**), [ERROR_REPORTING.md](ERROR_REPORTING.md), [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md).

## What the user sees

* **Help ▸ Check for Updates…** and **About ▸ Check for Updates…** check once, in the background.
* **File ▸ Settings… ▸ Updates**: *Automatically check for updates* (off by default), check
  interval (every day — the default when switched on —, every 3 days, every week), release channel
  (*Stable*, or *Prereleases as well*), the time of the last successful check, **Check Now** and
  the current status.
* Statuses: *Checking for updates…*, *Up to date*, *Update available*, *Unable to check*,
  *Verification failed*, *Updates not configured*. A server that cannot be reached, a rate limit,
  an invalid certificate or an unverifiable manifest is never reported as *Up to date*.
* When an update is available: installed version, available version, release date, release notes
  (shown as plain text), download size, and **Update Now** · **Remind Me Later**. The release notes
  can be read without starting anything. *Remind Me Later* postpones that version for one check
  interval (automatic checks only; a manual check always shows it).
* Automatic checks never open a dialog unless an update is available, and never run while the
  setting is off. No check runs at start-up before the main window is shown.

## Trust model

Monograph PDF does **not** trust GitHub, the network or a checksum on its own. An update is
installed only if all of the following hold:

1. **Signed release manifest.** Each release publishes `MonographPDF_update_manifest.json`. Its
   `signed` part (canonical JSON: sorted keys, no whitespace, ASCII, no floating-point numbers) is
   signed with **Ed25519**. The application embeds the trusted public keys in
   `resources/update/update_config.json` (bundled read-only inside the program; never read from a
   user-writable location). At least `threshold` distinct trusted keys must have signed; unknown
   keys, repeated signatures and malformed signatures never count.
2. **Identity.** The manifest names the product (`app_id` `monograph-pdf`), the Inno Setup AppId of
   Monograph PDF and the repository `aungyemun/monograph-pdf`.
3. **Channel and version.** `stable` manifests must carry `X.Y.Z`, `prerelease` manifests
   `X.Y.Z-label`; the stable channel refuses prerelease manifests. Versions are compared with
   Semantic Versioning precedence using ASCII digits only (independent of the Windows language and
   regional settings). Only a newer version is offered — **downgrades are refused** — and a
   manifest may require a minimum installed version (`min_upgrade_from`).
4. **Freshness and replay protection.** `issued` and `expires` (UTC) bound the validity; expired
   manifests fail verification, and a manifest dated more than 24 hours in the future is refused
   (clock check). Each manifest carries a `sequence` number that must grow with every manifest the
   maintainer signs; the application stores the highest sequence accepted per channel and refuses
   older ones (rollback / replay of outdated metadata).
5. **Artifact.** The manifest lists the Windows x64 Inno Setup installer with its exact name
   (`MonographPDF_<version>_Setup.exe`), HTTPS URL on an allowed host, size and **SHA-256**. The
   download must match the size and hash exactly and must be a Windows program (`MZ`), otherwise it
   is deleted.
6. **Authenticode (optional layer).** The installer's Windows signature is checked with
   `WinVerifyTrust` (revocation from the local cache only). Releases are **not code-signed today**
   ([CODE_SIGNING.md](CODE_SIGNING.md)), so this is recorded but only enforced when the
   configuration sets `require_authenticode` — to be switched on once releases are signed.

### Transport

* HTTPS only (`core/updates/net.py`), TLS 1.2 or later, certificate and host-name verification
  from the Windows certificate store. Verification is never disabled; there is no HTTP fallback.
* Every URL, including each redirect, must be HTTPS on an allowed host: `github.com`,
  `api.github.com`, `objects.githubusercontent.com`, `release-assets.githubusercontent.com`
  (GitHub's release download redirects). At most 5 redirects.
* Bounded sizes (manifest 256 KB, release list 2 MB, installer exactly the signed size), 20-second
  network timeouts, cancellable downloads, no cookies or credentials, no GitHub token. The only
  identifying header is `User-Agent: MonographPDF/<version> (+updater)`.
* Sources: the stable channel reads
  `https://github.com/aungyemun/monograph-pdf/releases/latest/download/MonographPDF_update_manifest.json`
  (no API rate limit); the prerelease channel lists releases through the GitHub REST API
  (unauthenticated, 60 requests per hour per address; a rate limit is reported as *Unable to check*)
  and takes the newest non-draft release that has a manifest.

### Why not TUF

[The Update Framework](https://theupdateframework.io/) gives stronger guarantees (separate root,
targets, snapshot and timestamp roles; a regularly re-signed timestamp that bounds freeze attacks).
It needs a repository layout with continuously refreshed timestamp metadata and an online or
scheduled signing role, which GitHub Releases does not provide by itself, and a new third-party
dependency in the application. For a single-maintainer project distributing one installer per
release, a narrowly scoped signed manifest gives authenticated metadata, integrity, identity,
downgrade and replay protection with no new runtime dependency. Its known limits:

* **Freeze attacks are bounded only by `expires`.** An attacker who controls the download path and
  replays the latest *valid* manifest can hide a newer release until that manifest expires. The
  release tool defaults to 365 days; publishing a shorter validity means re-signing the manifest of
  the current release before it expires (otherwise clients report *Verification failed*, never
  *Up to date*).
* **One key class.** There is no separate root key for rotating the signing key; key rotation
  ships a new public key in an application update signed by the old key. A compromised signing key
  requires a manual release with a new key and a security advisory.
* **No independent timestamp service.**

### Ed25519 implementation

The application verifies signatures with a small pure-Python implementation of RFC 8032
(`core/updates/ed25519.py`, verification ≈ 3 ms) instead of adding a cryptography library to the
installed program. Verification is strict (canonical encodings only, `S < L`, cofactorless
equation, like OpenSSL). It is tested against the RFC 8032 test vectors and cross-checked against
OpenSSL (through `cryptography`, a test-only dependency) on random keys and tampered signatures.
Signing in the same module is for offline maintainer tooling and tests only; it is not constant
time and must never run on a machine exposed to untrusted code.

## Manifest format

```json
{
  "signed": {
    "type": "monograph-pdf-update", "schema": 1,
    "app_id": "monograph-pdf", "inno_app_id": "{64FC0D97-5E17-405F-9461-D6C075E1B467}",
    "repository": "aungyemun/monograph-pdf",
    "version": "0.3.1", "channel": "stable", "release_date": "2026-11-02",
    "issued": "2026-11-02T09:00:00Z", "expires": "2027-11-02T09:00:00Z", "sequence": 7,
    "release_notes": "…plain text…",
    "release_page": "https://github.com/aungyemun/monograph-pdf/releases/tag/v0.3.1",
    "installed_size": 0,
    "min_upgrade_from": "0.2.0",
    "artifacts": [{"kind": "inno-setup", "os": "windows", "arch": "x64",
                   "name": "MonographPDF_0.3.1_Setup.exe",
                   "url": "https://github.com/aungyemun/monograph-pdf/releases/download/v0.3.1/MonographPDF_0.3.1_Setup.exe",
                   "size": 126718568, "sha256": "…64 hex…"}]
  },
  "signatures": [{"keyid": "…16 hex (SHA-256 of the public key)…", "sig": "…base64…"}]
}
```

## Maintainer tooling

`scripts/packaging/update_manifest.py` (offline; never publishes anything). Commands that use the
secret key must run in an interactive console window: the passphrase is read with `getpass`, never
from arguments, environment variables or files, and the secret key is never printed.

```powershell
# once: a new folder outside every Git working copy (refused otherwise; an existing key is never overwritten)
python scripts\packaging\update_manifest.py keygen --out <new folder>
# any time: check a key against the application's verification code (asks for the passphrase)
python scripts\packaging\update_manifest.py selftest --key <folder>\update-signing.key
# per release, after the release build (asks for the passphrase)
python scripts\packaging\update_manifest.py make --setup installer\MonographPDF_0.4.2_Setup.exe `
    --notes docs\releases\v0.4.2.md --channel stable --sequence <N> `
    --key <folder>\update-signing.key --out installer\MonographPDF_update_manifest.json
python scripts\packaging\update_manifest.py verify --manifest installer\MonographPDF_update_manifest.json
```

The sequence number must be larger than any sequence used before for that channel (keep a record
with the key; start at 1). A client that once accepted sequence *N* refuses every manifest below *N*.

## Production signing key

| | |
|---|---|
| Algorithm | Ed25519 (RFC 8032), 32-byte keys, 64-byte signatures (base64 in the manifest) |
| Key id | `27c3b3b23b949c40` (first 16 hex digits of the SHA-256 of the public key) |
| Public key | `13a02f80f8b1b009e5bb8ae77b15c766f06bf9ab2b640f91577b300ba552846c` |
| Fingerprint (SHA-256) | `27c3b3b23b949c4035fd8e70617adebc5451d4a5e7232a199da475a92c5d7ad2` |
| Created | 2026-10-23, offline on the maintainer's computer, from the operating system's CSPRNG |
| Trusted by | `resources/update/update_config.json` (bundled, read-only in the program folder), threshold 1 |

**Storage.** `keygen` writes two files into a new folder whose permissions it restricts to the
current Windows user: `update-signing.key` and `update-signing.pub.json` (public key, fingerprint and
the self-test results; no secret). The secret key is encrypted with the passphrase
(`scripts/packaging/signing_key.py`): scrypt (N = 2^17, r = 8, p = 1, a new 32-byte salt per file)
derives 64 bytes; the first 32 are XORed with the secret (used once, because the salt is new for
every file) and the last 32 key an HMAC-SHA256 over the whole file, so a wrong passphrase or any
change is detected; the decrypted key must reproduce the stored public key. The construction uses
only the Python standard library; it is not an established file format such as PKCS#8, which is a
deliberate trade-off against adding a cryptography library to the maintainer tooling. The key
is never in the repository, in a build folder, in CI or GitHub secrets, in an installer or in a
source archive (`*.key` is ignored by Git; `check_release.py` scans release archives for secrets).

**Backup.** Keep at least one offline copy of the *encrypted* `update-signing.key` (and
`update-signing.pub.json`) on separate removable media stored apart from the computer — for example
two USB drives in different places — and keep the passphrase separately (e.g. written down, or in a
password manager that is not on the same drive). Copy the files yourself; the tooling never copies the
key anywhere. Check a backup with `selftest --key <backup>\update-signing.key`.

**Loss of the key or passphrase.** Installed copies can no longer be updated automatically. Generate
a new key, ship its public key in a release that users install manually with Setup, and announce
this on the Releases page. Keep the encrypted backups to avoid this.

**Compromise.** Treat any exposure of the decrypted key, or of the key file together with its
passphrase, as a compromise. There is no online revocation: an attacker who also controls the
download path could sign a malicious manifest for installations that trust the key, until they
install a version that no longer trusts it. Respond with a new key, a release that trusts only the
new key (installed manually or, if the attacker cannot control the path, through an update signed
with the old key), a GitHub security advisory and a note on the Releases page.

## Key rotation

What the application implements: several trusted keys (`trusted_keys`, each identified by its key id),
a signature threshold (`threshold`; signatures by unknown or repeated keys never count, at most 8
signatures are read), and verification that ignores signatures from keys it does not trust. What it
does not implement: a separate root key, online revocation, or replacing keys from remote metadata —
trusted keys change only with the program itself.

Planned rotation: (1) generate the new key; (2) release *N* that trusts both keys (threshold 1) and
is signed with the old key; (3) once most installations run *N* or later, sign with the new key and,
in release *N+k*, remove the old key. Raising the threshold to 2 (two keys on separate media)
protects against one lost or stolen key at the cost of signing every release twice.

## GitHub Releases publishing

Signing happens locally; GitHub only hosts the files. For every release with updates switched on:

1. Build and verify the release as usual.
2. Sign the manifest locally with `update_manifest.py make` (interactive passphrase) with the next
   sequence number, then `verify`.
3. `verify_release.py --dir installer …` checks the manifest (*update-manifest*): it verifies with the
   release's own trusted keys exactly as the application does and must name this version, this
   Setup.exe (URL of tag `v<version>`, size, SHA-256) and stay valid for at least 30 more days.
4. Publish `MonographPDF_update_manifest.json` as a fourth release asset next to Setup.exe and the two
   ZIP files. The stable channel reads `releases/latest/download/MonographPDF_update_manifest.json`,
   so the newest stable release must always carry it; prereleases are found through the releases API
   and must carry it too to be offered.
5. Before the manifest expires (default 365 days), sign a fresh one for the current release with a
   higher sequence number and replace the asset; otherwise checks report *Verification failed*.

No GitHub secret or variable is needed for this procedure. The `production-release` environment
(branch `main`, tags `v*`; no secrets, no variables) is not used by any workflow. Automated signing in
GitHub Actions would require putting the secret key (or access to a remote signing service) into that
environment, a workflow that signs and uploads the manifest, and — strongly recommended then —
required reviewers on the environment; it would also make GitHub part of the trust chain. It is not
used.

## Production setup

1. ✅ Production Ed25519 key generated locally (2026-10-23), stored encrypted outside every Git
   working copy in a folder restricted to the maintainer's account; self-test passed. An offline
   backup is the maintainer's responsibility (see [Backup](#production-signing-key)).
2. ✅ Public key in `resources/update/update_config.json` (`trusted_keys`), `enabled` = `true`,
   threshold 1, no `ca_file`. A second key and threshold 2 are not used yet.
3. ✅ Manifest validity: 365 days by default; re-sign before expiry (see above).
4. ✅ `verify_release.py` checks the manifest of every release whose configuration has updates on.
5. Optional, not done: Authenticode signing and `require_authenticode`.
6. ❌ Not yet done: the end-to-end update test (`scripts/test_update_e2e.py`) of the packaged build
   and the 0.4.0 → 0.4.1 Setup upgrade on a disposable Windows installation (never on the
   maintainer's own Windows). Required before 0.4.1 is published.

`verify_release.py --layout` also fails a release whose bundled update or reporting configuration
differs from the repository's (so a test build's synthetic key, mock endpoint or test CA can never be
released).

## Testing

`tests/unit/test_update_crypto.py`, `test_update_manifest.py` (also: the shipped configuration trusts
exactly the production key and never a test key), `test_update_net.py` (local HTTPS mock server with a
generated test CA), `test_update_staging.py`, `test_update_install.py`, `test_update_ui.py` (also: no
network request at start-up), `test_update_signing_key.py` (encrypted key storage, console-only
passphrases, the self-test), `test_update_manifest_release_check.py` (the release check of the
manifest), `test_international.py`; the Windows end-to-end upgrade test is described in
[AUTOMATIC_UPGRADE_AND_CLEANUP.md](AUTOMATIC_UPGRADE_AND_CLEANUP.md#testing). All keys in the tests
are synthetic (`tests/fixtures/update_fixtures.py`). The production key's own self-test
(`update_manifest.py selftest`, 19 checks on fictional in-memory manifests that name a repository no
installation accepts) passed when the key was created.
