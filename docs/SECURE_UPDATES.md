# Secure updates

Status: **included since 0.3.0; switched on from 0.5.0** (the first published version with it) with the production update-signing key
(key id `27c3b3b23b949c40`). 0.3.0 and 0.4.0 ship with updates switched off and no trusted key, so
they cannot update themselves: users install the current version once with Setup from the
[GitHub Releases page](https://github.com/aungyemun/monograph-pdf/releases). 0.4.1 also had update checks
switched on but was never published, so 0.5.0 is the first published version with them; the first
upgrade through the updater is from 0.5.0 to a later release.

Validation status: the signing key, its backup and restore, the manifest checks and the user
interface are tested (see [Testing](#testing)). Installation, the 0.4.0 → 0.5.0 Setup upgrade and the
application on real Windows computers are tested by the maintainer
([WINDOWS_RELEASE_TEST_CHECKLIST.md](WINDOWS_RELEASE_TEST_CHECKLIST.md)). For 0.5.0 the maintainer
decided to publish first and carry out these tests afterwards; until then they are **not verified**,
and problems found go into 0.5.1.

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
* A failed check or update names the situation (`core/updates/messages.py`) — *No internet
  connection*, *GitHub is temporarily unavailable*, *No compatible release found*, *Invalid digital
  signature*, *Update information has expired*, *Update information has an invalid date*, *Update is
  for a different product*, *Unsupported upgrade path*, *Installer integrity verification failed*,
  *Download interrupted*, *Update canceled* — says that nothing was downloaded or installed, and
  offers **Open Releases Page** for a manual download. No security detail beyond that is shown.
  Checking again repeats the complete verification; nothing is ever accepted because the user
  retried, and an installer that failed verification is deleted, never run.
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
   manifests fail verification, a validity longer than **730 days** is refused, and a manifest dated
   more than 24 hours in the future is refused (clock check). Each manifest carries a `sequence` number that must grow with every manifest the
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
* Sources: **both** stable and prerelease channels discover candidates through the GitHub Releases
  REST API (`releases?per_page=20`; unauthenticated, 60 requests per hour per address; a rate limit
  is reported as *Unable to check*). Discovery picks the newest **Windows-line** non-draft release
  that publishes `MonographPDF_update_manifest.json` (stable skips GitHub prereleases and
  platform-suffixed tags such as `v0.1.0-macos-1` / `v0.1.0-linux`). The listing is only a hint —
  authenticity always comes from the Ed25519-signed manifest fetched next. The repository-wide
  GitHub “Latest” badge is **never** used (it may point at macOS or Linux).

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
  release tool signs for 730 days (see [Manifest expiry](#manifest-expiry)); published releases are
  immutable, so fresh update information requires a new release before the newest manifest expires
  (otherwise clients report *Verification failed*, never *Up to date*).
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
from arguments, environment variables or files (a console is detected with the Windows console API;
redirected input is refused rather than risking an echo), and the secret key is never printed.

| Command | Purpose |
|---|---|
| `keygen --out <new folder>` | new key (only for rotation or replacement); refuses Git working copies and used folders |
| `selftest --key <file> [--key <copy>] [--config] [--scan <folder>] [--report <file>]` | opens one or more copies with one prompt; same key in all, trusted by the configuration, OpenSSL and built-in Ed25519 sign identically, 19 verification checks, no unencrypted copy of the secret in the scanned folders (also inside ZIP files) |
| `export-pkcs8 --key <update-signing.key> --out <new .pem>` | standard PKCS#8 copy of the same key (below) |
| `make …` | signs a release manifest; refuses to write it unless both Ed25519 implementations agree and it verifies against `--config` |
| `verify --manifest <file> [--config]` | verifies exactly as the application does |

The application's `core` package loads the PDF engine, so the tools are normally run from a
**signing bundle**: `scripts/packaging/make_signing_bundle.py --out <new folder>` copies only the
needed files from a commit (with an empty `core/__init__.py`), `requirements-signing.txt` (the optional
`cryptography` wheels, pinned with SHA-256 hashes) and a file manifest. It runs in a separate Python
3.11 environment that contains nothing but those packages — never the build environment and never the
application. Without `cryptography`, the original key format, `selftest` and `verify` need only the
Python standard library.

```powershell
& $PY -I <bundle>\scripts\packaging\update_manifest.py make --setup installer\MonographPDF_0.5.0_Setup.exe `
    --notes docs\releases\v0.5.0.md --channel stable --sequence <N> `
    --key <key folder>\update-signing.pkcs8.pem --config resources\update\update_config.json `
    --out installer\MonographPDF_update_manifest.json
& $PY -I <bundle>\scripts\packaging\update_manifest.py verify --manifest installer\MonographPDF_update_manifest.json `
    --config resources\update\update_config.json
```

The sequence number must be larger than any sequence used before for that channel (keep a record
with the key; start at 1). A client that once accepted sequence *N* refuses every manifest below *N*;
a reused number would let two different manifests count as equally new.

## Production signing key

| | |
|---|---|
| Algorithm | Ed25519 (RFC 8032), 32-byte keys, 64-byte signatures (base64 in the manifest) |
| Key id | `27c3b3b23b949c40` (first 16 hex digits of the SHA-256 of the public key) |
| Public key | `13a02f80f8b1b009e5bb8ae77b15c766f06bf9ab2b640f91577b300ba552846c` |
| Fingerprint (SHA-256) | `27c3b3b23b949c4035fd8e70617adebc5451d4a5e7232a199da475a92c5d7ad2` |
| Created | 2026-10-23, offline on the maintainer's computer, from the operating system's CSPRNG |
| Trusted by | `resources/update/update_config.json` (bundled, read-only in the program folder), threshold 1 |

**Storage.** The key folder (outside every Git working copy, readable only by the maintainer's
Windows account) holds the same secret key in two encrypted files with the same passphrase, plus the
public `update-signing.pub.json`:

| File | Format | Status |
|---|---|---|
| `update-signing.pkcs8.pem` | Standard encrypted PKCS#8 (RFC 5958): PBES2 (RFC 8018) with scrypt (RFC 7914; N = 2^17, r = 8, p = 1, 16-byte salt) and AES-256-CBC (16-byte IV); password = passphrase in Unicode NFC as UTF-8. Decrypted by the maintained `cryptography` library (OpenSSL). | **current** (signing) |
| `update-signing.key` | Project format v1 (`signing_key.py`): scrypt (N = 2^17, r = 8, p = 1, 32-byte salt) → 64 bytes; 32 XORed with the secret (one-time key stream, new salt per file), 32 key an HMAC-SHA256 over the file (encrypt-then-MAC). Standard library only. | retained, unchanged (fallback) |

Review (2026-10-23): the original format's design is sound — a memory-hard KDF and authenticated
encryption — but it is the project's own construction and its decryption code is project code. The
PKCS#8 copy moves decryption to a maintained, widely used implementation and a standard container
without weakening the KDF. Findings that shaped it:

* `cryptography`'s `BestAvailableEncryption` for PKCS#8 (checked on 50.0.1) writes **PBKDF2-HMAC-SHA256
  with only 2048 iterations** — far cheaper to attack than scrypt N = 2^17 — so it is not used; the
  PKCS#8 file is written by `signing_key.export_pkcs8` with scrypt and AES-256-CBC from `cryptography`,
  and its encoding is checked against OpenSSL (`openssl pkey` decrypts the same encoding; tests).
* PBES2/AES-CBC has **no integrity tag**. `load_pkcs8` therefore requires `update-signing.pub.json`
  and refuses a key that does not reproduce exactly that public key (every tested change to the
  ciphertext is refused).
* OpenSSL's command line refuses scrypt parameters above 32 MiB, so it cannot open the production
  PKCS#8 file (N = 2^17 needs 128 MiB); `cryptography` can. Lowering N for that would weaken the key.
* Both files use the same passphrase and the same KDF cost, so keeping both does not make guessing
  easier. Neither file can be used without the passphrase.

Passphrases are read only by `getpass` in a real console, kept in memory for one command (several
copies open with one prompt), and never written; key files are created with exclusive-create (never
overwritten) in folders restricted to the current user; no temporary file ever holds the decrypted
key. The key is never in the repository, a build folder, CI or GitHub secrets, an installer or a
source archive (`*.key` and `*.pem` are ignored by Git; `check_release.py` scans release archives).

**Backup.** One ZIP holds both encrypted key files, the public key, the signing bundle, restore,
release-signing and emergency instructions, file checksums and a stand-alone `verify_backup.py`; it
is kept outside the repository and must be copied to separate offline media, with the passphrase
kept separately. It was restore-tested (extracted to a new folder, both key files opened from there,
self-test passed, no unencrypted secret found). No additional ZIP password is used: the keys inside
are already encrypted, and a second password would add a second thing to lose.

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
does **not** implement: a separate root key, remote revocation, or replacing keys from remote
metadata — trusted keys change only by installing a new version of the program.

| Scenario | Procedure | Installations that do not update |
|---|---|---|
| 1. Planned transition to a new key | Release *N* trusts old + new (threshold 1), signed with the old key; later releases signed with the new key; release *N+k* drops the old key | keep trusting only the old key until they install *N* |
| 2. Adding a second trusted key | Add it to `trusted_keys` (threshold 1) in a release signed with a key the installations already trust | — |
| 3. Requiring two signatures | A release trusting both keys sets `threshold` 2; from then on every manifest needs both signatures (`make --key A --key B`) | an installation with threshold 1 still accepts one signature until it updates |
| 4. Removing an obsolete key | Release that no longer lists it, signed with a key that stays | — |
| 5. Compromised key | New key; release *X* trusts **only** the new key. Sign *X*'s manifest with the compromised key *and* the new key: installations still accept the old signature and move to *X* automatically, which adds no risk because whoever holds the key can sign anyway. After *X*, never sign with the old key again. Security advisory and Releases-page notice telling users to install *X* (manually if in doubt) | remain exposed to manifests signed with the compromised key until they install *X* |
| 6. Key permanently lost | New key; release trusting it, installed **manually** (it cannot be signed for existing installations) | report *Verification failed* (never a false "up to date"); keep working offline |

Assessment: a second key kept on separate media (scenario 2) is the improvement that matters most —
it turns a lost key (6) into a planned transition (1). A root key or TUF-style roles would add
complexity a single-maintainer project would have to operate correctly for little practical gain;
not added.

### Recommendation: a pre-trusted recovery key (future release, not 0.5.0)

A recovery key only helps if installed copies **already trust it** when the primary key is lost:
a second key kept offline but not listed in `trusted_keys` is useless for recovery, because nothing
signed with it would be accepted. Recommended for a later release (for example 0.6.0), with
explicit approval:

1. Generate a separate recovery key on a different medium with a different passphrase; back it up
   like the primary key; never use it for routine releases.
2. Ship its public key in `trusted_keys` next to `27c3b3b23b949c40`, **threshold 1**, in a release
   signed with the primary key. From then on either key alone can sign.
3. If the primary key is lost: sign the next release with the recovery key (copies that trust it
   update normally) and introduce a new primary key the same way.
4. If the primary key is compromised: the recovery key signs a release that trusts only the recovery
   key and a new primary key (see scenario 5).

Trade-off: with threshold 1, either key can sign alone, so both must be protected equally well;
threshold 2 would protect against one stolen key but would turn one lost key into a blocked update
path. 0.5.0 keeps one key and threshold 1; copies installed before a recovery key is added must be
updated once (with the primary key) to benefit. No unsigned or weaker recovery path exists or will be
added.

## Direct upgrades and long-term compatibility

An installed copy reads only the **newest** manifest of its channel and compares it with its own
version: it never needs the manifests of versions it skipped, however many there are and however long
it has not checked. Replay protection does not depend on history either: the copy remembers the
highest sequence number it has accepted and refuses anything lower. So 0.5.0 can go straight to 0.7.0
or 1.0.0 with one **Update Now** (one download, one Setup run), provided the conditions below hold.
Every step still requires the user's click; automatic checks stay off by default and only check.

### Supported paths

| From | To | How | Verified |
|---|---|---|---|
| 0.3.0, 0.4.0 | 0.5.0 or later | **Setup** (manual): their update checks are switched off and trust no key | Setup upgrade 0.4.0 → 0.5.0: by the maintainer on real computers ([checklist](WINDOWS_RELEASE_TEST_CHECKLIST.md) A3); **not verified** at the 0.5.0 release (done after publication) |
| 0.5.0 or later | any newer release whose manifest is signed by a key the installed copy trusts, uses manifest schema 1, and whose `min_upgrade_from` (if any) is not newer than the installed version | **Update Now** (direct, no intermediate versions) | automated tests with synthetic keys (`test_update_direct_upgrade.py`); on real computers **not verified** until a release after 0.5.0 exists |
| 0.5.0 or later | a release whose manifest the copy cannot verify (only new keys, a newer manifest schema) | refused (*Verification failed*, "nothing was downloaded or installed", **Open Releases Page**); install with **Setup** | automated tests |
| 0.5.0 or later | a release with `min_upgrade_from` newer than the installed version | the update is shown, **Update Now** is disabled with the reason and a link to the release page; install with **Setup** | automated tests |
| any | an older version | never offered (downgrade refused) | automated tests |
| PDF Editor 0.1.5 | Monograph PDF | **Setup** migration | installer test matrix |

Setup itself always works as the manual path: it upgrades any earlier installation in place (same
AppId and folder) and keeps settings and documents.

### Settings and data across versions

* Settings (`preferences.json`) carry a layout number (`_schema`); each version runs every migration
  from the file's layout up to its own (`core/user_prefs.py`, `MIGRATIONS`, never removed). Values of
  the wrong type fall back to defaults; settings written by a newer version are kept unchanged; an
  unreadable file is copied aside before defaults are used; saving is atomic.
* Installation layout: Setup deletes and rewrites the program's `_internal` folder and removes files
  that the previous installation listed as its own (`installed_files.txt`), so files of any skipped
  version cannot linger; user files and documents are never touched.
* An interrupted download is deleted; an update handed to the helper whose computer was switched off
  is cleaned up at a later start; a failed Setup run is reported once and the old version keeps
  working ([AUTOMATIC_UPGRADE_AND_CLEANUP.md](AUTOMATIC_UPGRADE_AND_CLEANUP.md)).

### Rules for every future release (so that old copies can still upgrade directly)

1. Publish `MonographPDF_update_manifest.json` with **schema 1** under that name in this repository.
   A future format needs a new asset name, published *in addition* as long as older copies are
   supported.
2. Sign with key `27c3b3b23b949c40` — alone or together with newer keys — for as long as copies that
   trust only that key are supported. A release whose manifest is signed only by a newer key cannot
   be verified by copies that trust only that key (0.5.0 and later until a new key is added): they must upgrade with Setup (see [Key rotation](#key-rotation)).
3. Sequence numbers grow across all releases of a channel; never reset them.
4. Keep the Inno Setup AppId, the Setup file name pattern, a Windows x64 Inno Setup installer, and the
   switches the **old** helper passes (`/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /CURRENTUSER|/ALLUSERS
   /DIR= /LOG=`): the helper that runs the new Setup is the one installed with the old version.
5. Add a settings migration for any renamed or reinterpreted setting; never remove one.
6. Use `min_upgrade_from` only when a direct jump truly cannot work; the manual path is Setup.
7. Publish a release before the newest manifest expires ([Manifest expiry](#manifest-expiry)).

## Manifest expiry

Policy (from 0.5.0, the first published version with update checks): every manifest is valid for **730 days from its `issued` time**. The release
tool signs for exactly 730 days by default (`--expires-days` accepts 1–730), the application refuses
any manifest whose `expires − issued` exceeds 730 days (`MAX_VALIDITY` in `core/updates/manifest.py`)
or whose dates are malformed, out of order or not UTC (`…Z`), and `verify_release.py` requires at
least 30 days left when a release is published. All times are timezone-aware UTC. The validity
belongs to the **manifest**, not to the installation: a copy installed in 2026 that first checks in
2029 updates normally if the newest release's manifest is valid then.

Expiry limits how long a captured manifest can be replayed to hide newer releases (freeze attack) and
must never affect normal use: an expired manifest only makes the update check report *Update
information has expired*; opening, editing and saving keep working, offline or not. Interactions:

* **Immutable releases** are switched on for the repository: after publication a release's assets
  cannot change, so a manifest cannot be renewed in place. Fresh update information always comes with
  a **new release** (new version, new manifest, next sequence number). If no release is published
  before the newest manifest expires, checks fail safely until one is.
* Sequence numbers only grow; a renewal (= the next release) uses the next number. Never reset them —
  an installation that accepted *N* refuses everything below *N*.
* Clock checks: a manifest dated more than 24 hours in the future is refused; a computer whose clock
  is far ahead sees valid manifests as expired. Both fail safely.
* Note for future versions: 0.5.0 refuses manifests valid for more than 730 days. A later decision
  to sign longer-lived manifests would make them unverifiable for 0.5.0-era copies.

### Security assessment of 730 instead of 365 days

A longer validity does **not** make updates more secure; it is a trade-off for a project that may
release less often than once a year, made because published releases are immutable and a manifest
can only be renewed by a new release.

| Topic | Effect of 730 days |
|---|---|
| Replay of an outdated manifest | Unchanged for copies that have seen a newer one: the sequence check refuses anything older, whatever its expiry. |
| Freeze attack (hiding a newer release by serving the latest valid old manifest) | The window grows from up to 1 to up to 2 years. It needs an attacker who can serve content in place of GitHub over verified HTTPS (TLS interception with a trusted certificate, or control of the repository); then the copy sees "up to date" or an older version, never an unsigned or forged one. |
| First check of a new installation | The copy has no sequence history and accepts any valid manifest; with 730 days an attacker in the position above could offer a release up to 2 years old (still a genuine, signed release — never older than the installed version, since downgrades are refused). |
| Older installed copies | Benefit: they keep updating directly as long as the newest manifest is valid, even after a gap of up to 2 years between releases. |
| Clock manipulation | Unchanged rules: more than 24 hours in the future is refused; a clock set back can make an expired manifest look valid again, which only helps an attacker who already controls the computer. The 24-hour tolerance is kept (time zones, unsynchronised clocks). |
| Manifest rollback | Unchanged: sequence numbers. |
| Key rotation | A manifest signed with a key that is later retired stays valid up to 2 years: after a key **compromise**, publish the replacement release promptly (see [Key rotation](#key-rotation)). |
| Immutable releases | The reason for the change: a manifest cannot be renewed in place, so its validity must cover the expected time to the next release. |

Stronger design, not added in 0.5.0: TUF-style short-lived **timestamp** metadata (re-signed every
few days, e.g. by a scheduled job) would bound freeze attacks to days regardless of release
frequency, but needs an online or scheduled signing key and a mutable hosting location (immutable
releases cannot hold it). It would be a deliberate future design change, not a last-minute one.

## GitHub Releases publishing

Signing happens locally; GitHub only hosts the files. For every release with updates switched on:

1. Finalize the source code (everything committed).
2. Pass the automated tests (full suite, Windows CI).
3. Complete manual installation testing on real Windows computers
   ([WINDOWS_RELEASE_TEST_CHECKLIST.md](WINDOWS_RELEASE_TEST_CHECKLIST.md)) with a build of that commit.
4. Build the final release artifacts (`scripts\build_release.ps1`); `verify_release.py` passes.
5. Calculate the final installer hashes (the build writes `SHA256SUMS.txt`; `Get-FileHash`).
6. Generate the 730-day manifest and 7. sign it locally (`make`, interactive passphrase) with the
   next sequence number — one more than the highest number recorded in `SEQUENCE_LOG.txt` beside the
   key (a number used for a manifest that was signed but never published, such as one prepared for
   0.4.1, is used up); never reuse a number for a different manifest.
8. Verify its Ed25519 signature (`verify`) and 9. confirm the installer hash and size match
   (`verify_release.py --dir installer …` → `PASS update-manifest`: verified with the release's own
   trusted keys exactly as the application does; this version; this Setup.exe — URL of tag
   `v<version>`, size, SHA-256; valid 30+ days).
10. Prepare a **draft** GitHub release and 11. attach exactly four files: Setup.exe, the Installer
    and Source ZIPs and `MonographPDF_update_manifest.json`. Windows clients discover that release
    through the Releases API by selecting the newest Windows-line tag that carries the manifest
    asset — not through GitHub’s repository-wide Latest. Every published Windows release that
    should be discoverable must therefore include the signed manifest; prereleases need it too.
12. Independently verify the draft assets (download them into an empty folder; `verify`,
    `verify_release.py --dir <folder>`).
13. Publish only after explicit authorization — publication is irreversible (immutable releases).
    Never publish incomplete assets. Afterwards, **Check for Updates** on an installed copy.

### What the GitHub configuration enforces (checked 2026-10-23)

* Ruleset *Protect main branch*: `main` cannot be deleted or force-pushed.
* Ruleset *Protect production release tags* (`refs/tags/v*`): tags cannot be created, moved or deleted
  except by repository administrators (bypass). It does not check what a tag points to.
* **Immutable releases** are on: a published release's assets and tag cannot be changed afterwards
  (drafts can). This also means a manifest can only be renewed with a new release.
* Workflows have read-only `contents` permission; the only workflow (Windows CI) never builds,
  signs or publishes.
* The `production-release` environment (branch `main`, tags `v*`, no reviewers, no secrets, no
  variables) is **not referenced by any workflow**. Environment rules apply only to workflow jobs that
  name the environment, so it does **not** protect releases created manually (web page or `gh`): those
  are limited only by repository permissions and the rulesets above.

No GitHub secret or variable is needed: signing is local. Automated signing in GitHub Actions would
require putting the secret key (or access to a remote signing service) into that environment, a
workflow that signs and uploads the manifest, and — then essential — required reviewers on the
environment; it would also make GitHub part of the trust chain. It is not used. Recommendations:
keep administrator access to the repository to the maintainer's account with two-factor
authentication; keep immutable releases on.

## Production setup

1. ✅ Production Ed25519 key generated locally (2026-10-23), stored encrypted outside every Git
   working copy in a folder restricted to the maintainer's account; self-test passed; standard PKCS#8
   copy made; backup ZIP created and restore-tested. Copying it to offline media is the maintainer's
   step (see [Backup](#production-signing-key)).
2. ✅ Public key in `resources/update/update_config.json` (`trusted_keys`), `enabled` = `true`,
   threshold 1, no `ca_file`. A second key and threshold 2 are not used yet.
3. ✅ Manifest validity: 730 days, enforced as a maximum by the application ([Manifest expiry](#manifest-expiry)).
4. ✅ `verify_release.py` checks the manifest of every release whose configuration has updates on.
5. Optional, not done: Authenticode signing and `require_authenticode`.
6. Installation, 0.4.0 → 0.5.0 upgrade and application tests of the packaged build on real Windows
   computers ([WINDOWS_RELEASE_TEST_CHECKLIST.md](WINDOWS_RELEASE_TEST_CHECKLIST.md)), done by the
   maintainer: for 0.5.0 carried out after publication (not verified at release). The first
   **Update Now** through the updater can only be tested with the release after 0.5.0.

`verify_release.py --layout` also fails a release whose bundled update or reporting configuration
differs from the repository's (so a test build's synthetic key, mock endpoint or test CA can never be
released).

## Testing

`tests/unit/test_update_crypto.py`, `test_update_manifest.py` (also: the shipped configuration trusts
exactly the production key and never a test key), `test_update_net.py` (local HTTPS mock server with a
generated test CA), `test_update_staging.py`, `test_update_install.py`, `test_update_ui.py` (also: no
network request at start-up), `test_update_signing_key.py` (encrypted key storage, console-only
passphrases, the self-test), `test_update_signing_key_pkcs8.py` (PKCS#8 copy, tamper detection,
OpenSSL interoperability; needs `cryptography`), `test_update_signing_bundle.py` (signing bundle,
multi-copy self-test, secret scan), `test_update_manifest_release_check.py` (the release check of the
manifest), `test_update_direct_upgrade.py` (skipped versions, years between checks, expired newest
manifest, clock far behind, key-rotation bridge, refused paths, future manifest format, the switches an
old helper passes, interrupted downloads and installations), `test_user_prefs_migration.py` (settings
across versions), `test_international.py`; the Windows end-to-end upgrade test is described in
[AUTOMATIC_UPGRADE_AND_CLEANUP.md](AUTOMATIC_UPGRADE_AND_CLEANUP.md#testing). All keys in the tests
are synthetic (`tests/fixtures/update_fixtures.py`). The production key's own self-test
(`update_manifest.py selftest`, 19 checks on fictional in-memory manifests that name a repository no
installation accepts) passed when the key was created.
