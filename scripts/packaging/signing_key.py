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

The same secret can also be stored as a standard encrypted PKCS#8 file (``update-signing.pkcs8.pem``,
RFC 5958 EncryptedPrivateKeyInfo): PBES2 (RFC 8018) with the scrypt KDF (RFC 7914; N=2^17, r=8, p=1,
16-byte salt) and AES-256-CBC (16-byte IV), the same passphrase (NFC, UTF-8). It is read with the
maintained ``cryptography`` library (OpenSSL), so decryption does not depend on code in this project.
PKCS#8 has no integrity tag: a changed file is detected because the decrypted key must reproduce the
expected public key (``load_pkcs8``). Writing it needs ``cryptography`` (maintainer tooling only; the
application never uses it). Note: OpenSSL's ``openssl pkcs8``/``pkey`` commands refuse scrypt
parameters above 32 MiB of memory, so they cannot open this file; ``cryptography`` can.

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
PKCS8_FILE = "update-signing.pkcs8.pem"
PUBLIC_FILE = "update-signing.pub.json"
PEM_HEADER = "-----BEGIN ENCRYPTED PRIVATE KEY-----"
PEM_FOOTER = "-----END ENCRYPTED PRIVATE KEY-----"
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


# ---------------------------------------------------------------- standard PKCS#8 copy

_OID_PBES2 = "1.2.840.113549.1.5.13"
_OID_SCRYPT = "1.3.6.1.4.1.11591.4.11"
_OID_AES256_CBC = "2.16.840.1.101.3.4.1.42"


def _der(tag: int, content: bytes) -> bytes:
    n = len(content)
    if n < 0x80:
        length = bytes([n])
    else:
        raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
        length = bytes([0x80 | len(raw)]) + raw
    return bytes([tag]) + length + content


def _der_oid(dotted: str) -> bytes:
    parts = [int(x) for x in dotted.split(".")]
    body = bytes([40 * parts[0] + parts[1]])
    for value in parts[2:]:
        chunk = [value & 0x7F]
        value >>= 7
        while value:
            chunk.append(0x80 | (value & 0x7F))
            value >>= 7
        body += bytes(reversed(chunk))
    return _der(0x06, body)


def _der_int(value: int) -> bytes:
    # minimal two's-complement encoding of a non-negative integer (a leading 0 byte only when needed)
    return _der(0x02, value.to_bytes(max(1, (value.bit_length() + 8) // 8), "big"))


def _seq(*items: bytes) -> bytes:
    return _der(0x30, b"".join(items))


def _password(passphrase: str) -> bytes:
    return unicodedata.normalize("NFC", passphrase).encode("utf-8")


def export_pkcs8(secret: bytes, passphrase: str, *, n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P) -> bytes:
    """Encrypted PKCS#8 (PBES2 + scrypt + AES-256-CBC) PEM of a 32-byte Ed25519 secret."""
    from cryptography.hazmat.primitives import padding, serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    if len(secret) != 32:
        raise KeyFileError("an Ed25519 secret key has 32 bytes")
    plain = Ed25519PrivateKey.from_private_bytes(secret).private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    salt, iv = os.urandom(16), os.urandom(16)
    key = hashlib.scrypt(_password(passphrase), salt=salt, n=n, r=r, p=p, maxmem=512 * 1024 * 1024, dklen=32)
    padder = padding.PKCS7(128).padder()
    data = padder.update(plain) + padder.finalize()
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ct = enc.update(data) + enc.finalize()
    kdf = _seq(_der_oid(_OID_SCRYPT), _seq(_der(0x04, salt), _der_int(n), _der_int(r), _der_int(p)))
    scheme = _seq(_der_oid(_OID_AES256_CBC), _der(0x04, iv))
    der = _seq(_seq(_der_oid(_OID_PBES2), _seq(kdf, scheme)), _der(0x04, ct))
    import base64

    b64 = base64.b64encode(der).decode("ascii")
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return ("\n".join([PEM_HEADER, *lines, PEM_FOOTER]) + "\n").encode("ascii")


def describe_pkcs8(pem: bytes) -> dict:
    """Algorithms and parameters of an encrypted PKCS#8 file (no passphrase needed)."""
    import base64

    text = pem.decode("ascii").strip()
    if not (text.startswith(PEM_HEADER) and text.endswith(PEM_FOOTER)):
        raise KeyFileError("not an encrypted PKCS#8 PEM file")
    der = base64.b64decode("".join(text.splitlines()[1:-1]), validate=True)
    found: list = []

    def walk(b: bytes) -> None:
        i = 0
        while i < len(b):
            tag, ln = b[i], b[i + 1]
            i += 2
            if ln & 0x80:
                k = ln & 0x7F
                ln = int.from_bytes(b[i:i + k], "big")
                i += k
            v = b[i:i + ln]
            i += ln
            if tag == 0x06:
                parts, x = [v[0] // 40, v[0] % 40], 0
                for c in v[1:]:
                    x = (x << 7) | (c & 0x7F)
                    if not c & 0x80:
                        parts.append(x)
                        x = 0
                found.append(".".join(map(str, parts)))
            elif tag == 0x02:
                found.append(int.from_bytes(v, "big"))
            elif tag == 0x04:
                found.append(len(v))
            elif tag == 0x30:
                walk(v)

    walk(der)
    if found[:2] != [_OID_PBES2, _OID_SCRYPT] or found[6:7] != [_OID_AES256_CBC]:
        raise KeyFileError("unsupported PKCS#8 encryption (expected PBES2 + scrypt + AES-256-CBC)")
    return {"scheme": "PBES2", "kdf": "scrypt", "salt_bytes": found[2], "n": found[3], "r": found[4],
            "p": found[5], "cipher": "AES-256-CBC", "iv_bytes": found[7], "ciphertext_bytes": found[8]}


def load_pkcs8(pem: bytes, passphrase: str, expected_public: bytes) -> bytes:
    """Decrypt with ``cryptography``; the key must reproduce ``expected_public`` (integrity check)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    params = describe_pkcs8(pem)
    if params["n"] < 2**14 or params["salt_bytes"] < 16:
        raise KeyFileError("the PKCS#8 file uses weaker scrypt parameters than allowed")
    try:
        key = serialization.load_pem_private_key(pem, password=_password(passphrase))
    except (ValueError, TypeError):
        raise KeyFileError("wrong passphrase, or the PKCS#8 file is damaged") from None
    if not isinstance(key, Ed25519PrivateKey):
        raise KeyFileError("the PKCS#8 file does not hold an Ed25519 key")
    secret = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                               serialization.NoEncryption())
    if ed25519.public_key(secret) != expected_public:
        raise KeyFileError("the decrypted key does not match the expected public key")
    return secret


def expected_public_for(path: Path) -> bytes:
    """Public key a PKCS#8 file must reproduce: from ``update-signing.pub.json`` beside it."""
    pub = path.parent / PUBLIC_FILE
    try:
        data = json.loads(pub.read_text(encoding="utf-8"))
        pk = bytes.fromhex(data["public_key"])
        if len(pk) != 32 or data.get("keyid") != key_id(pk):
            raise ValueError
        return pk
    except (OSError, ValueError, KeyError, TypeError):
        raise KeyFileError(f"{PUBLIC_FILE} beside the PKCS#8 file is missing or invalid") from None


def sign_with_cryptography(secret: bytes, message: bytes) -> bytes | None:
    """Ed25519 signature from OpenSSL through ``cryptography`` (None when it is not installed)."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        return None
    return Ed25519PrivateKey.from_private_bytes(secret).sign(message)


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


# Passphrases entered in this process (memory only, never written), so that one command can open
# several copies of the same key (e.g. the original and the PKCS#8 file) with a single prompt.
_ENTERED: list[str] = []


def _with_passphrase(keyid: str, open_with) -> bytes:
    for pw in _ENTERED:
        try:
            return open_with(pw)
        except KeyFileError:
            continue
    pw = ask_passphrase(keyid)
    secret = open_with(pw)  # raises KeyFileError on a wrong passphrase
    _ENTERED.append(pw)
    return secret


def forget_passphrases() -> None:
    _ENTERED.clear()


def load_secret(path: Path) -> bytes:
    """Secret of a key file: an encrypted file asks for its passphrase (once per process); a plain
    64-hex file (synthetic test keys only) is read directly with a warning."""
    if inside_git_checkout(path):
        raise SystemExit("refusing to use a signing key stored inside a Git working copy")
    text = path.read_text(encoding="ascii").strip()
    if text.startswith(PEM_HEADER):
        try:
            expected = expected_public_for(path)
            pem = text.encode("ascii")
            return _with_passphrase(key_id(expected), lambda pw: load_pkcs8(pem, pw, expected))
        except KeyFileError as exc:
            raise SystemExit(f"cannot use the signing key: {exc}") from None
        except ImportError:
            raise SystemExit("reading a PKCS#8 key needs the 'cryptography' package (signing environment)") from None
    if is_encrypted(text):
        try:
            doc = json.loads(text)
            read_public(doc)
            return _with_passphrase(doc["keyid"], lambda pw: decrypt(doc, pw))
        except (ValueError, KeyFileError) as exc:
            raise SystemExit(f"cannot use the signing key: {exc}") from None
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise SystemExit("the key file must be an encrypted key file or hold 64 lowercase hex digits")
    print("warning: unencrypted signing key (allowed for synthetic test keys only)", file=sys.stderr)
    return bytes.fromhex(text)


def secret_traces(secret: bytes) -> list[bytes]:
    """Byte patterns that would reveal the secret if found in a file (raw, hex, base64, unencrypted
    PKCS#8 DER and its base64)."""
    import base64

    traces = [secret, secret.hex().encode(), secret.hex().upper().encode(), base64.b64encode(secret)]
    der_prefix = bytes.fromhex("302e020100300506032b657004220420")  # PKCS#8 Ed25519 private key header
    der = der_prefix + secret
    traces += [der, base64.b64encode(der)[:40]]
    return traces


def scan_for_secret(folder: Path, secret: bytes) -> list[str]:
    """Files under ``folder`` that contain the secret in any common unencrypted encoding (also inside
    ZIP archives)."""
    import zipfile

    traces = secret_traces(secret)
    hits = []
    for f in sorted(folder.rglob("*")):
        if not f.is_file():
            continue
        data = f.read_bytes()
        if any(t in data for t in traces):
            hits.append(str(f))
        if zipfile.is_zipfile(f):
            with zipfile.ZipFile(f) as z:
                for name in z.namelist():
                    if any(t in z.read(name) for t in traces):
                        hits.append(f"{f}!{name}")
    return hits
