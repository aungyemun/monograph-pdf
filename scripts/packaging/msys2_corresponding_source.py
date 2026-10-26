"""Rebuild MSYS2 corresponding-source archives when official ``*.src.tar.zst`` URLs 404.

MSYS2 eventually drops old ``mingw/sources/*.src.tar.zst`` packages from the public
mirror while the binary DLLs shipped in a Monograph PDF release remain pinned. For
each OCR component that records ``msys2.recipe_commit``, this module reconstructs an
equivalent corresponding-source tarball from:

* the ``MINGW-packages`` recipe (PKGBUILD + patches) at that exact commit, and
* the upstream release archives named in the PKGBUILD ``source`` / ``sha256sums`` arrays.

The resulting ``*.corresponding-source.tar.gz`` is deterministic (sorted members,
fixed 1980-01-01 mtime / gzip header) and verified by SHA-256 recorded in
``third_party_sources.json``.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import re
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "MonographPDF-source-archive"
GITHUB_RAW = "https://raw.githubusercontent.com/msys2/MINGW-packages/{commit}/{package}/{name}"
ZIP_EPOCH = 315532800  # 1980-01-01 UTC


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _http_get(url: str, dest: Path | None = None, *, timeout: int = 120) -> bytes:
    if not url.startswith("https://"):
        raise RuntimeError(f"refusing non-HTTPS URL: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    part: Path | None = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"network error for {url}: {exc.reason}") from exc
    if dest is not None:
        part = dest.with_suffix(dest.suffix + ".part")
        try:
            part.write_bytes(data)
            part.replace(dest)
        finally:
            if part is not None and part.exists():
                part.unlink(missing_ok=True)
    return data


def _bash_array(text: str, name: str) -> list[str]:
    """Parse a simple Bash array assignment ``name=(...)`` from a PKGBUILD."""
    m = re.search(rf"(?ms)^{re.escape(name)}=\((.*?)\)", text)
    if not m:
        return []
    body = m.group(1)
    body = re.sub(r"#.*?$", "", body, flags=re.M)
    return [tok.strip("'\"") for tok in re.findall(r"""'[^']*'|"[^"]*"|\S+""", body) if tok.strip("'\"")]


def _expand_braces(token: str) -> list[str]:
    """Expand a single ``prefix{a,b}suffix`` (used for ``file{,.sig}``)."""
    m = re.search(r"^([^{]*)\{([^}]*)\}(.*)$", token)
    if not m:
        return [token]
    prefix, choices, suffix = m.group(1), m.group(2), m.group(3)
    out: list[str] = []
    for choice in choices.split(","):
        out.extend(_expand_braces(prefix + choice + suffix))
    return out


def _expand_vars(s: str, *, pkgver: str, realname: str) -> str:
    s = s.replace("${_realname}", realname).replace("$_realname", realname)
    s = s.replace("${pkgver}", pkgver).replace("$pkgver", pkgver)

    def subst(match: re.Match[str]) -> str:
        var = match.group(1)
        if var == "pkgver":
            value = pkgver
        elif var == "_realname":
            value = realname
        else:
            return match.group(0)
        op = match.group(2) or ""
        if op.startswith("%."):  # ${pkgver%.*}
            return value.rsplit(".", 1)[0] if "." in value else value
        if op.startswith(":") and ":" in op[1:]:  # ${pkgver:0:4}
            _, rest = op.split(":", 1)
            start_s, _, length_s = rest.partition(":")
            start = int(start_s or "0")
            length = int(length_s) if length_s else None
            return value[start : start + length] if length is not None else value[start:]
        if op.startswith(":"):  # ${pkgver:0}
            start = int(op[1:] or "0")
            return value[start:]
        return value

    return re.sub(r"\$\{(pkgver|_realname)([^}]*)\}", subst, s)


def parse_pkgbuild(text: str) -> list[tuple[str, str]]:
    """Return ``[(source, sha256_or_SKIP), ...]`` from a PKGBUILD."""
    pkgver_m = re.search(r"(?m)^pkgver=([^\n]+)", text)
    realname_m = re.search(r"(?m)^_realname=([^\n]+)", text)
    ver = pkgver_m.group(1).strip().strip("'\"") if pkgver_m else ""
    real = realname_m.group(1).strip().strip("'\"") if realname_m else ""

    # Tokenizer splits ``"url"{,.sig}`` into ``url`` and ``{,.sig}``; rejoin before brace expand.
    tokens = _bash_array(text, "source")
    joined: list[str] = []
    i = 0
    while i < len(tokens):
        if i + 1 < len(tokens) and tokens[i + 1].startswith("{") and tokens[i + 1].endswith("}"):
            joined.append(tokens[i] + tokens[i + 1])
            i += 2
        else:
            joined.append(tokens[i])
            i += 1
    raw_sources: list[str] = []
    for tok in joined:
        expanded = _expand_vars(tok, pkgver=ver, realname=real)
        raw_sources.extend(_expand_braces(expanded))
    sums = [s.lower() for s in _bash_array(text, "sha256sums")]
    if len(raw_sources) != len(sums):
        raise RuntimeError(
            f"PKGBUILD source/sha256sums length mismatch ({len(raw_sources)} vs {len(sums)})"
        )
    return list(zip(raw_sources, sums))


def package_dir_name(source_package: str) -> str:
    """``mingw-w64-glib2-2.80.2-2.src.tar.zst`` → ``mingw-w64-glib2``."""
    name = source_package
    for suffix in (".corresponding-source.tar.gz", ".src.tar.zst", ".src.tar.gz"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    parts = name.split("-")
    # strip trailing -pkgver-pkgrel when pkgver starts with a digit
    if len(parts) >= 3 and re.match(r"^\d", parts[-1]) and re.match(r"^\d", parts[-2]):
        parts = parts[:-2]
    return "-".join(parts)


def corresponding_archive_name(source_package: str) -> str:
    base = source_package
    if base.endswith(".src.tar.zst"):
        base = base[: -len(".src.tar.zst")]
    elif base.endswith(".corresponding-source.tar.gz"):
        return source_package
    return f"{base}.corresponding-source.tar.gz"


def _add_tar_bytes(tf: tarfile.TarFile, arcname: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    info.mtime = ZIP_EPOCH
    info.mode = 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    tf.addfile(info, io.BytesIO(data))


def _rm_tree(path: Path) -> None:
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), reverse=True):
        try:
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        except OSError:
            pass
    try:
        path.rmdir()
    except OSError:
        pass


def materialize(comp: dict, cache: Path, *, offline: bool = False) -> Path:
    """Build or reuse the corresponding-source archive for an OCR/MSYS2 component."""
    msys = comp.get("msys2") or {}
    commit = msys.get("recipe_commit")
    source_package = msys.get("source_package") or (comp["files"][0]["name"] if comp.get("files") else "")
    if not commit or not source_package:
        raise RuntimeError(f"{comp.get('id')}: msys2.recipe_commit / source_package required")
    package = package_dir_name(
        source_package if source_package.endswith((".src.tar.zst", ".corresponding-source.tar.gz"))
        else source_package + ".src.tar.zst"
    )
    # Prefer the name already recorded on the file entry (after refresh).
    out_name = None
    if comp.get("files"):
        out_name = comp["files"][0].get("name")
    if not out_name or out_name.endswith(".src.tar.zst"):
        out_name = corresponding_archive_name(source_package)
    dest = cache / out_name
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    if offline:
        raise RuntimeError(
            f"{out_name}: not in cache and offline mode cannot rebuild MSYS2 corresponding source"
        )

    work = cache / f".rebuild-{comp['id']}"
    _rm_tree(work)
    work.mkdir(parents=True)

    try:
        pkgbuild = _http_get(GITHUB_RAW.format(commit=commit, package=package, name="PKGBUILD"))
        (work / "PKGBUILD").write_bytes(pkgbuild)
        pairs = parse_pkgbuild(pkgbuild.decode("utf-8", errors="replace"))
        members: list[tuple[str, bytes]] = [("PKGBUILD", pkgbuild)]

        for src, expect in pairs:
            name = Path(src).name
            if expect == "skip":
                # Detached signatures and similar: provenance lives in PKGBUILD; skip download.
                continue
            if src.startswith("https://") or src.startswith("http://"):
                if not src.startswith("https://"):
                    raise RuntimeError(f"refusing non-HTTPS upstream URL: {src}")
                local = work / name
                print(f"  msys2 upstream {name}")
                _http_get(src, local)
                data = local.read_bytes()
            else:
                url = GITHUB_RAW.format(commit=commit, package=package, name=name)
                print(f"  msys2 recipe file {name}")
                data = _http_get(url)
                (work / name).write_bytes(data)
            got = hashlib.sha256(data).hexdigest()
            if got != expect:
                raise RuntimeError(f"{name}: SHA-256 {got} does not match PKGBUILD {expect}")
            members.append((name, data))

        part = dest.with_suffix(dest.suffix + ".part")
        members.sort(key=lambda x: x[0])
        prefix = out_name.replace(".corresponding-source.tar.gz", "") + "/"
        try:
            with open(part, "wb") as raw:
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=ZIP_EPOCH, compresslevel=9) as gz:
                    with tarfile.open(fileobj=gz, mode="w|") as tf:
                        for name, data in members:
                            _add_tar_bytes(tf, prefix + name, data)
            part.replace(dest)
        finally:
            if part.exists():
                part.unlink(missing_ok=True)
        return dest
    finally:
        _rm_tree(work)


def refresh_component_files(comp: dict, cache: Path) -> None:
    """Replace obsolete ``*.src.tar.zst`` file entries with the corresponding-source archive."""
    # Force rebuild name before materialize uses files[0].name
    old = comp["msys2"]["source_package"]
    new_name = corresponding_archive_name(old)
    if comp.get("files"):
        # Temporary name so materialize writes the new archive even if cache holds old zst.
        comp["files"][0]["name"] = new_name
    path = materialize(comp, cache, offline=False)
    digest = sha256_of(path)
    package = package_dir_name(old if old.endswith(".src.tar.zst") else old + ".src.tar.zst")
    urls = [
        GITHUB_RAW.format(
            commit=comp["msys2"]["recipe_commit"],
            package=package,
            name="PKGBUILD",
        ),
    ]
    comp["files"] = [
        {
            "name": path.name,
            "sha256": digest,
            "urls": urls,
            "verified_by": (
                "Rebuilt corresponding source from MSYS2 MINGW-packages recipe_commit "
                f"{comp['msys2']['recipe_commit']} plus upstream archives named in PKGBUILD "
                "(official *.src.tar.zst removed from repo.msys2.org)"
            ),
            "build": "msys2-corresponding",
        }
    ]
    comp["msys2"]["source_package"] = path.name
    comp["msys2"]["corresponding_source"] = True
    notes = comp.get("notes") or ""
    marker = "Corresponding source is reconstructed"
    if marker not in notes:
        extra = (
            " Corresponding source is reconstructed from the pinned MSYS2 recipe commit and "
            "upstream archives (official *.src.tar.zst no longer published for this package)."
        )
        comp["notes"] = (notes.rstrip() + extra).strip()
