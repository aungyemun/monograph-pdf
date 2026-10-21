"""Code-signing providers and the production signing gate (docs/CODE_SIGNING_POLICY.md).

Windows Authenticode signing is **separate** from Monograph PDF's update authentication: updates are
trusted only through the Ed25519-signed release manifest (core/updates), whatever certificate — or
none — signs the executables. Nothing here touches update keys, and core/updates never imports this.

Providers
* ``none``     — default for every build: nothing is signed; builds report "not signed".
* ``signtool`` — Windows SDK signtool.exe with a certificate already in the Windows certificate store
                 or on a hardware token, chosen by SHA-1 thumbprint (MONOGRAPH_SIGN_CERT_SHA1) and an
                 RFC 3161 timestamp server (MONOGRAPH_SIGN_TIMESTAMP_URL). No key file is ever read.
* ``signpath`` — SignPath (for example SignPath Foundation's free OSS certificate). SignPath signs
                 artifacts built by a verified CI build and requires a manual approval in SignPath for
                 every request; this provider only checks that the project is configured
                 (MONOGRAPH_SIGNPATH_ORGANIZATION_ID, _PROJECT_SLUG, _POLICY_SLUG) and refuses local
                 signing: submission belongs in a CI workflow (docs/CODE_SIGNING_POLICY.md).

Production gate: a production signing run needs an approval record for exactly this version and
commit, created by the Signing Approver with ``sign_release.py approve`` (typed confirmation), and a
clean working tree at that commit. Development builds never need it and are never signed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPROVALS = ROOT / "build" / "signing"
PRODUCT_NAME = "Monograph PDF"
PROVIDERS = ("none", "signtool", "signpath")


class SigningError(Exception):
    pass


def git(*args: str, root: Path = ROOT) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SigningError(f"git {' '.join(args)} failed") from exc


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------ approval


def approval_path(version: str, root: Path = ROOT) -> Path:
    return root / "build" / "signing" / f"approval-{version}.json"


def confirmation_phrase(version: str) -> str:
    return f"SIGN MONOGRAPH PDF {version}"


def create_approval(version: str, approver: str, confirmation: str, *, root: Path = ROOT,
                    now: datetime | None = None) -> Path:
    """The Signing Approver's decision for one version at one commit (typed confirmation required)."""
    if confirmation != confirmation_phrase(version):
        raise SigningError(f'approval not confirmed: type exactly "{confirmation_phrase(version)}"')
    if not approver.strip():
        raise SigningError("the approver's name is required")
    commit = git("rev-parse", "HEAD", root=root)
    if git("status", "--porcelain", "--untracked-files=no", root=root):
        raise SigningError("the working tree has uncommitted changes; approve a committed state only")
    record = {"schema": 1, "product": PRODUCT_NAME, "version": version, "commit": commit,
              "approver": approver.strip(),
              "approved_at": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    path = approval_path(version, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    return path


def check_approval(version: str, *, root: Path = ROOT) -> dict:
    """Raise SigningError unless production signing of ``version`` at HEAD was approved."""
    path = approval_path(version, root)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SigningError(f"no signing approval for {version} ({path.relative_to(root)}); the Signing Approver "
                           "must run: scripts/signing/sign_release.py approve") from None
    head = git("rev-parse", "HEAD", root=root)
    problems = []
    if record.get("product") != PRODUCT_NAME or record.get("version") != version:
        problems.append("the approval is for another product or version")
    if record.get("commit") != head:
        problems.append(f"the approval is for commit {str(record.get('commit'))[:12]}, not HEAD {head[:12]}")
    if git("status", "--porcelain", "--untracked-files=no", root=root):
        problems.append("the working tree has uncommitted changes")
    file_version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if file_version != version:
        problems.append(f"VERSION is {file_version}, not {version}")
    if problems:
        raise SigningError("production signing refused: " + "; ".join(problems))
    return record


# ------------------------------------------------------------------ providers


@dataclass
class SignResult:
    signed: list[str] = field(default_factory=list)
    unsigned: list[str] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)


class Provider:
    name = "base"

    def __init__(self, env: dict | None = None) -> None:
        self.env = dict(os.environ if env is None else env)

    def check_configuration(self) -> None:
        """Raise SigningError when the provider cannot sign on this machine."""

    def sign(self, files: list[Path], *, dry_run: bool = False) -> SignResult:
        raise NotImplementedError


class NoneProvider(Provider):
    """Development and unsigned builds: nothing is signed, and that is reported."""

    name = "none"

    def sign(self, files: list[Path], *, dry_run: bool = False) -> SignResult:
        return SignResult(unsigned=[str(f) for f in files])


class SigntoolProvider(Provider):
    name = "signtool"
    THUMB = "MONOGRAPH_SIGN_CERT_SHA1"
    TIMESTAMP = "MONOGRAPH_SIGN_TIMESTAMP_URL"

    def _signtool(self) -> str:
        explicit = self.env.get("MONOGRAPH_SIGNTOOL", "")
        if explicit:
            return explicit
        found = shutil.which("signtool.exe") or shutil.which("signtool")
        if found:
            return found
        kits = Path(self.env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Kits" / "10" / "bin"
        cands = sorted(kits.glob("10.*/x64/signtool.exe"), reverse=True) if kits.is_dir() else []
        if cands:
            return str(cands[0])
        raise SigningError("signtool.exe (Windows SDK) was not found; set MONOGRAPH_SIGNTOOL")

    def check_configuration(self) -> None:
        thumb = self.env.get(self.THUMB, "")
        if not re.fullmatch(r"[0-9A-Fa-f]{40}", thumb):
            raise SigningError(f"{self.THUMB} must be the 40-hex-digit SHA-1 thumbprint of a certificate in the "
                               "Windows certificate store or on a hardware token (no key files are used)")
        url = self.env.get(self.TIMESTAMP, "")
        if not url.startswith("https://") and not url.startswith("http://"):
            raise SigningError(f"{self.TIMESTAMP} must name an RFC 3161 timestamp server")

    def sign(self, files: list[Path], *, dry_run: bool = False) -> SignResult:
        self.check_configuration()
        tool = "signtool.exe" if dry_run else self._signtool()
        res = SignResult()
        for f in files:
            cmd = [tool, "sign", "/sha1", self.env[self.THUMB], "/fd", "SHA256", "/tr", self.env[self.TIMESTAMP],
                   "/td", "SHA256", "/d", PRODUCT_NAME, str(f)]
            res.commands.append(cmd)
            if dry_run:
                continue
            if subprocess.run(cmd).returncode != 0:
                raise SigningError(f"signtool failed for {f.name}")
            res.signed.append(str(f))
        return res


class SignPathProvider(Provider):
    name = "signpath"
    KEYS = ("MONOGRAPH_SIGNPATH_ORGANIZATION_ID", "MONOGRAPH_SIGNPATH_PROJECT_SLUG", "MONOGRAPH_SIGNPATH_POLICY_SLUG")

    def check_configuration(self) -> None:
        missing = [k for k in self.KEYS if not self.env.get(k)]
        if missing:
            raise SigningError("SignPath is not configured for this project (" + ", ".join(missing) + "); "
                               "Monograph PDF has no SignPath project today")

    def sign(self, files: list[Path], *, dry_run: bool = False) -> SignResult:
        self.check_configuration()
        raise SigningError("SignPath signing requests are submitted by the release-signing CI workflow from a "
                           "verified build, and approved manually in SignPath; they are never sent from a "
                           "local build (docs/CODE_SIGNING_POLICY.md)")


def provider(name: str, env: dict | None = None) -> Provider:
    try:
        return {"none": NoneProvider, "signtool": SigntoolProvider, "signpath": SignPathProvider}[name](env)
    except KeyError:
        raise SigningError(f"unknown signing provider {name!r}; use one of {', '.join(PROVIDERS)}") from None


def sign_files(name: str, version: str, files: list[Path], *, production: bool, env: dict | None = None,
               root: Path = ROOT, dry_run: bool = False) -> SignResult:
    """The one entry point used by the release build."""
    prov = provider(name, env)
    if name == "none":
        if production:
            raise SigningError("a production release must name a signing provider; 'none' leaves it unsigned")
        return prov.sign(files)
    if not production:
        raise SigningError("signing is only done for an approved production release (--production)")
    check_approval(version, root=root)
    missing = [f for f in files if not Path(f).is_file()]
    if missing:
        raise SigningError(f"missing files: {', '.join(map(str, missing))}")
    return prov.sign([Path(f) for f in files], dry_run=dry_run)


# ------------------------------------------------------------------ verification


def authenticode_status(path: Path) -> str:
    """'Valid', 'NotSigned', ... from Get-AuthenticodeSignature (Windows); 'unavailable' elsewhere."""
    if not sys.platform.startswith("win"):
        return "unavailable"
    ps = f"(Get-AuthenticodeSignature -LiteralPath '{str(path).replace(chr(39), chr(39) * 2)}').Status.ToString()"
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    return out.stdout.strip() or "unknown"
