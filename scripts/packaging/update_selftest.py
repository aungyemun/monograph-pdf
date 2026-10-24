"""Self-test of an update-signing key against the application's own verification code.

Run by ``update_manifest.py keygen`` (right after a new key is written) and ``selftest``. Every
manifest it signs is fictional and exists in memory only; none is written to disk or published.
To make sure such a manifest can never be accepted by a real installation, each names the
repository ``monograph-pdf-selftest/never-published`` (real installations require
``aungyemun/monograph-pdf``) and expires 10 minutes after it was issued.

Only check names and PASS/FAIL are reported; the secret key is never printed.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import sys
import tempfile
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.updates import config as update_config  # noqa: E402
from core.updates import ed25519, manager, net  # noqa: E402
from core.updates.install_target import InstallTarget  # noqa: E402
from core.updates.manifest import ManifestError, format_time, parse_and_verify, sign_manifest  # noqa: E402
from core.updates.state import UpdateState  # noqa: E402

SELFTEST_REPO = "monograph-pdf-selftest/never-published"
VERSION = "9.9.9"


def _config(public: bytes, *, threshold: int = 1) -> update_config.UpdateConfig:
    real = update_config.load(ROOT / "resources" / "update" / "update_config.json")
    return replace(real, enabled=True, repository=SELFTEST_REPO, trusted_keys={update_config.key_id(public): public},
                   threshold=threshold, ca_file=None)


def _signed(setup: bytes, now: datetime, **over) -> dict:
    name = f"MonographPDF_{over.get('version', VERSION)}_Setup.exe"
    s = {
        "type": "monograph-pdf-update", "schema": 1,
        "app_id": update_config.APP_ID, "inno_app_id": update_config.INNO_APP_ID,
        "repository": SELFTEST_REPO, "version": VERSION, "channel": "stable",
        "release_date": now.date().isoformat(), "issued": format_time(now),
        "expires": format_time(now + timedelta(minutes=10)), "sequence": 5,
        "release_notes": "Fictional self-test release; never published.",
        "release_page": f"https://github.com/{SELFTEST_REPO}/releases/tag/v{VERSION}",
        "installed_size": 0,
        "artifacts": [{"kind": "inno-setup", "os": "windows", "arch": "x64", "name": name,
                       "url": f"https://github.com/{SELFTEST_REPO}/releases/download/v{VERSION}/{name}",
                       "size": len(setup), "sha256": hashlib.sha256(setup).hexdigest()}],
    }
    s.update(over)
    return s


def _bytes(doc: dict) -> bytes:
    return json.dumps(doc).encode("utf-8")


def run_checks(secret: bytes) -> list[tuple[str, bool]]:
    public = ed25519.public_key(secret)
    cfg = _config(public)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    setup = b"MZ" + os.urandom(4094)
    good = sign_manifest(_signed(setup, now), [secret])
    results: list[tuple[str, bool]] = []

    def rejected(doc_bytes: bytes, config=cfg, when=None) -> bool:
        try:
            parse_and_verify(doc_bytes, config, now=when or now)
        except ManifestError:
            return True
        return False

    # 1-3 valid manifest is accepted, the same check the application runs
    try:
        rel = parse_and_verify(_bytes(good), cfg, now=now)
        ok = str(rel.version) == VERSION and rel.key_ids == (update_config.key_id(public),)
    except ManifestError:
        ok = False
    results.append(("valid manifest signed with this key is accepted", ok))

    # 4 changed signed metadata
    t = copy.deepcopy(good)
    t["signed"]["release_notes"] = "changed after signing"
    results.append(("changed release metadata is rejected", rejected(_bytes(t))))
    t = copy.deepcopy(good)
    t["signed"]["version"] = "9.9.10"
    results.append(("changed version is rejected", rejected(_bytes(t))))

    # 5 changed installer checksum (in the manifest) and a downloaded file that does not match
    t = copy.deepcopy(good)
    t["signed"]["artifacts"][0]["sha256"] = hashlib.sha256(b"other").hexdigest()
    results.append(("changed installer checksum is rejected", rejected(_bytes(t))))
    with tempfile.TemporaryDirectory(prefix="mpdf-selftest-") as tmp:
        old = os.environ.get("MONOGRAPH_PDF_UPDATES_DIR")
        os.environ["MONOGRAPH_PDF_UPDATES_DIR"] = str(Path(tmp) / "Updates")
        try:
            rel = parse_and_verify(_bytes(good), cfg, now=now)

            def fake_download(_cfg, _url, dest, size, _cancel, _report):
                Path(dest).write_bytes(b"MZ" + b"\0" * (size - 2))  # right size, wrong content

            try:
                manager.download_and_verify(cfg, rel, InstallTarget(ok=True), threading.Event(), downloader=fake_download)
                ok = False
            except manager.UpdateError as exc:
                left = [p for p in Path(tmp, "Updates").rglob("*") if p.is_file() and "lock" not in p.name.lower()]
                ok = exc.code == "verify" and not left
            results.append(("tampered installer download is rejected and deleted", ok))
        finally:
            if old is None:
                os.environ.pop("MONOGRAPH_PDF_UPDATES_DIR", None)
            else:
                os.environ["MONOGRAPH_PDF_UPDATES_DIR"] = old

    # 6 unknown signing key
    other = os.urandom(32)
    results.append(("manifest signed by an unknown key is rejected",
                    rejected(_bytes(sign_manifest(_signed(setup, now), [other])))))
    results.append(("this key is rejected by a configuration that does not trust it",
                    rejected(_bytes(good), _config(ed25519.public_key(other)))))

    # 7 malformed signatures
    def with_sigs(sigs):
        d = copy.deepcopy(good)
        d["signatures"] = sigs
        return _bytes(d)

    kid = good["signatures"][0]["keyid"]
    raw = base64.b64decode(good["signatures"][0]["sig"])
    flipped = bytes([raw[0] ^ 1]) + raw[1:]
    malformed = [
        ("no signatures", []),
        ("bad base64", [{"keyid": kid, "sig": "not base64!"}]),
        ("short signature", [{"keyid": kid, "sig": base64.b64encode(raw[:63]).decode()}]),
        ("one changed bit", [{"keyid": kid, "sig": base64.b64encode(flipped).decode()}]),
        ("S not reduced", [{"keyid": kid, "sig": base64.b64encode(raw[:32] + (2**255 - 1).to_bytes(32, "little")).decode()}]),
        ("wrong key id", [{"keyid": "0" * 16, "sig": good["signatures"][0]["sig"]}]),
    ]
    results.append(("malformed signatures are rejected (" + ", ".join(n for n, _ in malformed) + ")",
                    all(rejected(with_sigs(s)) for _, s in malformed)))

    # 8 unauthorized download locations
    def url_doc(url):
        s = _signed(setup, now)
        s["artifacts"][0]["url"] = url
        return _bytes(sign_manifest(s, [secret]))

    name = f"MonographPDF_{VERSION}_Setup.exe"
    bad_urls = [f"https://evil.example/{name}", f"http://github.com/x/{name}",
                f"https://user:pw@github.com/x/{name}", "https://github.com/x/other.exe"]
    results.append(("signed manifests with unauthorized installer URLs are rejected",
                    all(rejected(url_doc(u)) for u in bad_urls)))
    try:
        net.fetch_bytes(cfg, "https://evil.example/manifest.json", 1024)
        ok = False
    except net.NetworkError as exc:
        ok = exc.kind == "redirect"
    results.append(("the network layer refuses hosts outside the allow-list (no connection made)", ok))

    # 9 downgrade and replay (discovery uses the Releases API listing, never Latest)
    manifest = _bytes(good)
    listing = json.dumps([{
        "tag_name": f"v{VERSION}", "draft": False, "prerelease": False,
        "assets": [{"name": "MonographPDF_update_manifest.json",
                    "browser_download_url": f"https://github.com/{SELFTEST_REPO}/releases/download/v{VERSION}/"
                                           "MonographPDF_update_manifest.json"}],
    }]).encode("utf-8")

    def fetch(_c, url, *_a, **_k):
        return listing if "api.github.com" in url or url.rstrip("/").endswith("/api/releases") or "/releases?" in url else manifest

    res = manager.check(cfg, "stable", "10.0.0", UpdateState(), fetch=fetch, now=now)
    blocked = manager.install_permitted(parse_and_verify(manifest, cfg, now=now), "10.0.0")
    results.append(("an older version is not offered and cannot be installed (downgrade)",
                    res.status == manager.UpdateStatus.UP_TO_DATE and bool(blocked)))
    st = UpdateState(sequence={"stable": 6})
    res = manager.check(cfg, "stable", "0.4.1", st, fetch=fetch, now=now)
    results.append(("an older manifest sequence is refused (replay)", res.status == manager.UpdateStatus.VERIFICATION_FAILED))
    res = manager.check(cfg, "stable", "0.4.1", UpdateState(), fetch=fetch, now=now)
    results.append(("a newer verified version is offered", res.status == manager.UpdateStatus.AVAILABLE))

    # 10 expiry and clock
    results.append(("an expired manifest is rejected", rejected(_bytes(good), when=now + timedelta(minutes=11))))
    results.append(("a manifest dated more than 24 h in the future is rejected",
                    rejected(_bytes(good), when=now - timedelta(hours=25))))

    # 11 threshold
    twice = copy.deepcopy(good)
    twice["signatures"] = good["signatures"] * 2
    results.append(("a threshold of 2 is not met by one key signing twice",
                    rejected(_bytes(twice), _config(public, threshold=2))))
    both = sign_manifest(_signed(setup, now), [secret, other])
    results.append(("a threshold of 2 is not met by this key plus an untrusted key",
                    rejected(_bytes(both), _config(public, threshold=2))))

    # identity: the fictional manifest can never satisfy a real installation
    real = update_config.load(ROOT / "resources" / "update" / "update_config.json")
    real = replace(real, enabled=True, trusted_keys={update_config.key_id(public): public})
    results.append(("self-test manifests are rejected by the real repository identity", rejected(_bytes(good), real)))
    t = sign_manifest(_signed(setup, now, channel="stable", version="9.9.9-rc.1",
                              artifacts=[{**_signed(setup, now)["artifacts"][0],
                                          "name": "MonographPDF_9.9.9-rc.1_Setup.exe",
                                          "url": f"https://github.com/{SELFTEST_REPO}/releases/download/v9.9.9-rc.1/MonographPDF_9.9.9-rc.1_Setup.exe"}]),
                      [secret])
    results.append(("a prerelease version on the stable channel is rejected", rejected(_bytes(t))))
    return results


def report(results: list[tuple[str, bool]]) -> str:
    lines = [f"{'PASS' if ok else 'FAIL'}  {name}" for name, ok in results]
    passed = sum(ok for _, ok in results)
    lines.append(f"{passed}/{len(results)} checks passed")
    return "\n".join(lines)
