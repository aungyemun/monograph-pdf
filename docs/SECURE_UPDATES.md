# Secure updates

Status: **included since 0.3.0, switched off (also in 0.4.0)**. The update system is implemented and tested with synthetic
keys and local mock servers. It is **switched off** in every build until a production signing key
exists and the configuration below has been validated (see [Production setup](#production-setup)).
Until then, **Help ▸ Check for Updates…** reports "Updates not configured" — never "Up to date" —
and new versions come from the [GitHub Releases page](https://github.com/aungyemun/monograph-pdf/releases).

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

`scripts/packaging/update_manifest.py` (offline; never publishes anything):

```powershell
# once, on an offline or encrypted medium — refused inside the project folder
python scripts\packaging\update_manifest.py keygen --out E:\monograph-signing
# per release, after the release build
python scripts\packaging\update_manifest.py make --setup installer\MonographPDF_0.3.1_Setup.exe `
    --notes docs\releases\v0.3.1.md --channel stable --sequence 7 `
    --key E:\monograph-signing\update-signing.key --out installer\MonographPDF_update_manifest.json
python scripts\packaging\update_manifest.py verify --manifest installer\MonographPDF_update_manifest.json
```

The sequence number must be larger than any sequence used before (keep a record with the key).

## Production setup

Production update installation stays disabled until **all** of these are done and reviewed:

1. Generate the production Ed25519 key on an offline machine; store the secret key encrypted,
   with an offline backup; never in the repository, CI secrets, the application or a release.
2. Put the public key into `resources/update/update_config.json` (`trusted_keys`), set `enabled`
   to `true`, keep `ca_file` absent, and consider a second key and `threshold`.
3. Decide the manifest validity (`--expires-days`) and the re-signing routine.
4. Publish `MonographPDF_update_manifest.json` as an asset of every release (stable and
   prerelease), and add it to the release checklist and `verify_release.py`.
5. Optional: sign releases with Authenticode and set `require_authenticode`.
6. Test the complete path against the real GitHub release of a test repository or a draft
   prerelease, on a real Windows installation, before the first production release that has updates
   enabled. `verify_release.py --layout` fails a release whose bundled update or reporting
   configuration differs from the repository's (so a test build's synthetic key, mock endpoint or
   test CA can never be released).

## Testing

`tests/unit/test_update_crypto.py`, `test_update_manifest.py`, `test_update_net.py` (local HTTPS
mock server with a generated test CA), `test_update_staging.py`, `test_update_install.py`,
`test_update_ui.py`, `test_international.py`; the Windows end-to-end upgrade test is described in
[AUTOMATIC_UPGRADE_AND_CLEANUP.md](AUTOMATIC_UPGRADE_AND_CLEANUP.md#testing). All keys in the tests
are synthetic (`tests/fixtures/update_fixtures.py`).
