"""Passphrase-protected storage of the update-signing secret key (maintainer tooling only).

The application never reads this file and never contains a secret key; it only verifies signatures
with the public keys in ``resources/update/update_config.json`` (docs/SECURE_UPDATES.md).

File ``update-signing.key`` (JSON, ASCII)::

    {"format": "monograph-pdf-update-signing-key", "version": 1, "algorithm": "Ed25519",
     "keyid": "<16 hex>", "public_key": "<64 hex>", "created": "<UTC>",
     "kdf": {"name": "scrypt", "n": 131072, "r": 8, "p": 1, "salt": "<64 hex>"},
     "cipher": "scrypt-keystream-xor+hmac-sha256", "ciphertext": "<64 hex>", "mac": "<64 hex>"}

Encryption uses only the Python standard library (no extra dependency for the maintainer):

* scrypt (N=2^17, r=8, p=1, 32-byte random salt per file) derives 64 bytes from the passphrase;
* the first 32 bytes are XORed with the 32-byte secret. The salt is new for every file, so this
  key stream is used exactly once (a one-time pad drawn from a memory-hard KDF);
* the last 32 bytes key an HMAC-SHA256 over every other field (wrong passphrase or any change to
  the file is detected before the secret is used);
* after decryption the public key is recomputed and must equal the stored one.

The passphrase is read with ``getpass`` from an interactive console only — never from command-line
arguments, environment variables or files — and is never printed or logged.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.updates import ed25519  # noqa: E402
from core.updates.config import key_id  # noqa: E402

FORMAT = "monograph-pdf-update-signing-key"
CIPHER = "scrypt-keystream-xor+hmac-sha256"
KEY_FILE = "update-signing.key"
PUBLIC_FILE = "update-signing.pub.json"
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**17, 8, 1
MIN_PASSPHRASE = 12
_HEX32 = re.compile(r"^[0-9a-f]{64}$")


class KeyFileError(ValueError):
    pass


def fingerprint(public: bytes) -> str:
    """Full SHA-256 of the 32-byte public key (the key id is its first 16 hex digits)."""
    return hashlib.sha256(public).hexdigest()


def _derive(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    pw = unicodedata.normalize("NFC", passphrase).encode("utf-8")
    return hashlib.scrypt(pw, salt=salt, n=n, r=r, p=p, maxmem=512 * 1024 * 1024, dklen=64)


def _mac_input(doc: dict) -> bytes:
    body = {k: v for k, v in doc.items() if k != "mac"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def encrypt(secret: bytes, passphrase: str, *, created: str | None = None) -> dict:
    if len(secret) != 32:
        raise KeyFileError("an Ed25519 secret key has 32 bytes")
    salt = os.urandom(32)
    k = _derive(passphrase, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    pub = ed25519.public_key(secret)
    doc = {
        "format": FORMAT, "version": 1, "algorithm": "Ed25519",
        "keyid": key_id(pub), "public_key": pub.hex(),
        "created": created or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kdf": {"name": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P, "salt": salt.hex()},
        "cipher": CIPHER,
        "ciphertext": bytes(a ^ b for a, b in zip(secret, k[:32])).hex(),
    }
    doc["mac"] = hmac.new(k[32:], _mac_input(doc), hashlib.sha256).hexdigest()
    return doc


def is_encrypted(text: str) -> bool:
    return text.lstrip().startswith("{")


def read_public(doc: dict) -> bytes:
    if not isinstance(doc, dict) or doc.get("format") != FORMAT or doc.get("version") != 1:
        raise KeyFileError("not a Monograph PDF update-signing key file")
    pub = doc.get("public_key")
    if not isinstance(pub, str) or not _HEX32.match(pub) or doc.get("keyid") != key_id(bytes.fromhex(pub)):
        raise KeyFileError("the key file's public key or key id is invalid")
    return bytes.fromhex(pub)


def decrypt(doc: dict, passphrase: str) -> bytes:
    pub = read_public(doc)
    kdf = doc.get("kdf")
    if doc.get("cipher") != CIPHER or doc.get("algorithm") != "Ed25519" or not isinstance(kdf, dict) \
            or kdf.get("name") != "scrypt":
        raise KeyFileError("unsupported key file encryption")
    n, r, p, salt = kdf.get("n"), kdf.get("r"), kdf.get("p"), kdf.get("salt")
    if not (isinstance(n, int) and 2**14 <= n <= 2**20 and n & (n - 1) == 0 and r == 8
            and isinstance(p, int) and 1 <= p <= 4 and isinstance(salt, str) and _HEX32.match(salt)):
        raise KeyFileError("unsupported key file parameters")
    ct, mac = doc.get("ciphertext"), doc.get("mac")
    if not (isinstance(ct, str) and _HEX32.match(ct) and isinstance(mac, str) and _HEX32.match(mac)):
        raise KeyFileError("the key file is damaged")
    k = _derive(passphrase, bytes.fromhex(salt), n, r, p)
    if not hmac.compare_digest(hmac.new(k[32:], _mac_input(doc), hashlib.sha256).hexdigest(), mac):
        raise KeyFileError("wrong passphrase, or the key file was changed")
    secret = bytes(a ^ b for a, b in zip(bytes.fromhex(ct), k[:32]))
    if ed25519.public_key(secret) != pub:
        raise KeyFileError("the decrypted key does not match its public key")
    return secret


# ---------------------------------------------------------------- console and file system


def _stdin_is_console() -> bool:
    stdin = sys.stdin
    if stdin is None or stdin is not sys.__stdin__ or not stdin.isatty():
        return False
    if sys.platform.startswith("win"):
        # isatty() is also true for NUL and other character devices: ask Windows for a console
        import ctypes
        import msvcrt

        try:
            handle = msvcrt.get_osfhandle(stdin.fileno())
        except OSError:
            return False
        mode = ctypes.c_uint32()
        return bool(ctypes.windll.kernel32.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(mode)))
    return True


def require_console() -> None:
    """getpass echoes or fails without a real console; refuse instead of risking an echo."""
    if not _stdin_is_console():
        raise SystemExit("A passphrase can only be entered in an interactive console window.")


def _getpass(prompt: str) -> str:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)  # never fall back to echoing input
        try:
            return getpass.getpass(prompt)
        except getpass.GetPassWarning:
            raise SystemExit("The passphrase could not be read without showing it; nothing was done.") from None


def ask_new_passphrase() -> str:
    require_console()
    for _ in range(3):
        first = _getpass(f"New passphrase for the signing key (at least {MIN_PASSPHRASE} characters): ")
        if len(first) < MIN_PASSPHRASE:
            print(f"Too short: use at least {MIN_PASSPHRASE} characters.")
            continue
        if _getpass("Repeat the passphrase: ") != first:
            print("The two entries differ. Try again.")
            continue
        return first
    raise SystemExit("No passphrase set; nothing was written.")


def ask_passphrase(keyid: str) -> str:
    require_console()
    return _getpass(f"Passphrase of signing key {keyid}: ")


def inside_git_checkout(path: Path) -> bool:
    """True when ``path`` lies in this project or in any Git working copy (e.g. the build clone)."""
    p = path.resolve()
    try:
        p.relative_to(ROOT.resolve())
        return True
    except ValueError:
        pass
    return any((parent / ".git").exists() for parent in (p, *p.parents))


def restrict_to_current_user(folder: Path) -> str:
    """Windows: remove inherited permissions so only the current user can open the folder.

    Returns a short status for the record (never raises: the caller reports a failure)."""
    if not sys.platform.startswith("win"):
        try:
            os.chmod(folder, 0o700)
            return "chmod 700"
        except OSError as exc:
            return f"not restricted ({type(exc).__name__})"
    import subprocess

    from core.safe_paths import windows_tool

    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".lstrip("\\")
    if not os.environ.get("USERNAME"):
        return "not restricted (user name unknown)"
    res = subprocess.run([windows_tool("icacls.exe"), str(folder), "/inheritance:r", "/grant:r",
                          f"{user}:(OI)(CI)F"], capture_output=True, text=True, check=False)
    return "current user only (icacls)" if res.returncode == 0 else f"not restricted (icacls exit {res.returncode})"


def write_new(path: Path, text: str) -> None:
    """Create ``path``; never overwrite an existing file."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii", newline="\n") as fh:
        fh.write(text)


def load_secret(path: Path) -> bytes:
    """Secret of a key file: an encrypted file asks for its passphrase; a plain 64-hex file (synthetic
    test keys only) is read directly with a warning."""
    if inside_git_checkout(path):
        raise SystemExit("refusing to use a signing key stored inside a Git working copy")
    text = path.read_text(encoding="ascii").strip()
    if is_encrypted(text):
        try:
            doc = json.loads(text)
            read_public(doc)
            return decrypt(doc, ask_passphrase(doc["keyid"]))
        except (ValueError, KeyFileError) as exc:
            raise SystemExit(f"cannot use the signing key: {exc}") from None
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise SystemExit("the key file must be an encrypted key file or hold 64 lowercase hex digits")
    print("warning: unencrypted signing key (allowed for synthetic test keys only)", file=sys.stderr)
    return bytes.fromhex(text)
