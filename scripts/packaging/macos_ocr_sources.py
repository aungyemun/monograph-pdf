"""Provenance, corresponding source and release checks for the macOS OCR engine.

The macOS .app bundles a conda-forge Tesseract and its library closure (see stage_ocr_macos.py).
Every conda package ships its rendered build recipe — upstream source URL + SHA-256, patches and
build scripts — and the conda-forge feedstock commit it was built from. This module turns that
into evidence that can be checked:

``lock``       Write the explicit conda spec (package URL + SHA-256) of the OCR environment, so
               scripts/vendor_ocr_macos.sh recreates exactly the builds the inventory describes.
``inventory``  Record, for each package owning a bundled file: package file + SHA-256, license,
               feedstock commit, upstream sources (URL + SHA-256 as declared by the recipe) and the
               SHA-256 of every bundled file, verified equal to the hash conda recorded for that
               package file (so the bundled binary is byte-identical to the published package).
``sources``    Download every upstream source, verify it against the recipe's SHA-256 (never trust a
               URL alone), and write one deterministic ``<name>-<version>-<build>.corresponding-source.tar.gz``
               per package: upstream archive(s) + complete recipe (patches, build scripts) + licenses.
``check``      Release gate: fails unless the bundle matches the inventory byte for byte, every
               package's license files are in the bundle, every recipe patch is present, every
               upstream source is pinned by SHA-256, and every copyleft package has a verified
               corresponding-source archive (``sources --all`` adds them for permissive ones too).

Usage:
  python scripts/packaging/macos_ocr_sources.py lock      <ocr-env prefix> <out.lock>
  python scripts/packaging/macos_ocr_sources.py inventory <ocr-env prefix> <staged engines/ocr> <out.json>
  python scripts/packaging/macos_ocr_sources.py sources   <ocr-env prefix> <inventory.json> <out dir> [--all]
  python scripts/packaging/macos_ocr_sources.py check     <staged engines/ocr> <inventory.json> <sources dir>
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

COPYLEFT = ("GPL", "LGPL", "MPL")
EPOCH = 315532800  # 1980-01-01 UTC: deterministic archive members
USER_AGENT = "MonographPDF-source-archive"
SCHEMA = 1


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------------- recipe parsing


def recipe_sources(recipe_dir: Path) -> list[dict]:
    """Upstream sources declared by a rendered conda recipe (rattler-build or conda-build).

    Only ``url`` + ``sha256`` pairs are returned; anything else (git sources, md5-only) is
    reported as ``{"unresolved": ...}`` so the release check can refuse it.
    """
    for name in ("rendered_recipe.yaml", "meta.yaml"):
        path = recipe_dir / name
        if path.is_file():
            return _parse_source_block(path.read_text(encoding="utf-8", errors="replace"))
    return [{"unresolved": f"no rendered recipe in {recipe_dir}"}]


def recipe_patches(recipe_dir: Path) -> dict[str, str | None]:
    """Patch files named in the recipe's source block → SHA-256 (``None`` when missing)."""
    for name in ("rendered_recipe.yaml", "meta.yaml"):
        path = recipe_dir / name
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            break
    else:
        return {}
    block = text.split("source:", 1)[1].split("\nbuild:", 1)[0] if "source:" in text else ""
    names = sorted(set(re.findall(r"[\w.+-]+\.(?:patch|diff)\b", block)))
    found = {p.name: p for p in recipe_dir.rglob("*") if p.is_file()}
    return {n: (sha256_file(found[n]) if n in found else None) for n in names}


def _parse_source_block(text: str) -> list[dict]:
    lines = text.splitlines()
    out: list[dict] = []
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)source:\s*$", line)
        if not m:
            continue
        indent = len(m.group(1))
        block = []
        for nxt in lines[i + 1:]:
            depth = len(nxt) - len(nxt.lstrip())
            # YAML may write the list items at the key's own indent ("source:\n- url: …")
            if nxt.strip() and (depth < indent or (depth == indent and not nxt.lstrip().startswith("- "))):
                break
            block.append(nxt)
        out.extend(_entries(block))
        break
    return out or [{"unresolved": "no source block"}]


def _entries(block: list[str]) -> list[dict]:
    entries: list[dict] = []
    current: dict = {}
    pending_urls = False
    for raw in block:
        line = raw.strip()
        starts_item = raw.lstrip().startswith("- ") and ("url:" in line or "git" in line or "path:" in line)
        if starts_item and current:
            entries.append(current)
            current = {}
        body = line[2:] if line.startswith("- ") else line
        if body.startswith("url:"):
            value = body[4:].strip().strip("'\"")
            if value:
                current.setdefault("urls", []).append(value)
                pending_urls = False
            else:
                pending_urls = True
            continue
        if pending_urls and line.startswith("- ") and "://" in line:
            current.setdefault("urls", []).append(line[2:].strip().strip("'\""))
            continue
        pending_urls = False
        if body.startswith("sha256:"):
            current["sha256"] = body[7:].strip().strip("'\"").lower()
        elif body.startswith(("git_url:", "git:")):
            current["git"] = body.split(":", 1)[1].strip()
        elif body.startswith(("git_rev:", "rev:", "tag:")):
            current["git_rev"] = body.split(":", 1)[1].strip()
        elif body.startswith(("fn:", "file_name:")):
            current["fn"] = body.split(":", 1)[1].strip().strip("'\"")
    if current:
        entries.append(current)
    resolved = []
    for e in entries:
        if e.get("urls") and re.fullmatch(r"[0-9a-f]{64}", e.get("sha256", "")):
            resolved.append({"urls": e["urls"], "sha256": e["sha256"],
                             "fn": e.get("fn") or e["urls"][0].rsplit("/", 1)[-1]})
        elif e:
            resolved.append({"unresolved": json.dumps(e, sort_keys=True)})
    return resolved


# --------------------------------------------------------------------------- inventory


def _records(prefix: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((prefix / "conda-meta").glob("*.json"))]


def write_lock(prefix: Path, out: Path) -> int:
    lines = ["# Monograph PDF macOS OCR engine — exact conda-forge builds (osx-arm64).",
             "# Regenerate: python scripts/packaging/macos_ocr_sources.py lock tools/ocr-env <this file>",
             "@EXPLICIT"]
    records = _records(prefix)
    lines += sorted(f"{r['url']}#{r['sha256']}" for r in records)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(records)


def build_inventory(prefix: Path, staged: Path) -> dict:
    owners: dict[str, dict] = {}
    for record in _records(prefix):
        for rel in record.get("files", ()):
            owners[rel] = record
    bundled = {"bin/tesseract": staged / "bin" / "tesseract"}
    bundled.update({f"lib/{p.name}": p for p in sorted((staged / "lib").glob("*.dylib"))})
    packages: dict[str, dict] = {}
    for rel, path in bundled.items():
        record = owners.get(rel)
        if record is None:
            raise LookupError(f"{rel} is not owned by any conda package in {prefix}")
        entry = packages.setdefault(record["name"], {"record": record, "binaries": {}})
        entry["binaries"][rel] = path
    components = []
    for name, entry in sorted(packages.items()):
        record = entry["record"]
        expected = {p["_path"]: p for p in record.get("paths_data", {}).get("paths", [])}
        binaries = {}
        for rel, path in sorted(entry["binaries"].items()):
            info = expected.get(rel)
            target = (prefix / rel).resolve().relative_to(prefix.resolve()).as_posix()
            info = expected.get(target, info)
            actual = sha256_file(path)
            # "sha256" is the file as published in the package (before conda patched the install
            # prefix into it); the bundle must carry exactly those bytes.
            recorded = (info or {}).get("sha256")
            if recorded != actual:
                raise ValueError(f"{rel}: bundled sha256 {actual} != published {name} package file {recorded}")
            binaries[f"engines/ocr/{rel}"] = actual
        pkg_dir = Path(record.get("extracted_package_dir", ""))
        about = json.loads((pkg_dir / "info" / "about.json").read_text(encoding="utf-8"))
        extra = about.get("extra") or {}
        license_id = record.get("license", "")
        components.append({
            "id": f"macos-ocr-{name}",
            "name": name,
            "version": record["version"],
            "build": record.get("build", ""),
            "license": license_id,
            "copyleft": any(tag in license_id for tag in COPYLEFT),
            "home": about.get("home") or "",
            "conda_package": {
                "fn": record.get("fn", ""),
                "url": record.get("url", ""),
                "sha256": record.get("sha256", ""),
                "channel": record.get("channel", ""),
                "subdir": record.get("subdir", ""),
            },
            "feedstock": {"url": extra.get("remote_url", ""), "commit": extra.get("sha", "")},
            "upstream_sources": recipe_sources(pkg_dir / "info" / "recipe"),
            "patches": recipe_patches(pkg_dir / "info" / "recipe"),
            "binaries": binaries,
            "license_dir": f"engines/ocr/licenses/{name}",
            "corresponding_source": None,
        })
    return {"schema": SCHEMA, "platform": "macos-arm64", "engine": "tesseract", "components": components}


# --------------------------------------------------------------------------- corresponding source


def _fetch(urls: list[str], sha256: str, cache: Path) -> tuple[bytes, str]:
    cached = cache / sha256
    if cached.is_file() and sha256_file(cached) == sha256:
        return cached.read_bytes(), "cache"
    errors = []
    for url in urls:
        for candidate in dict.fromkeys([url.replace("http://", "https://", 1), url]):
            try:
                req = urllib.request.Request(candidate, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310 — fixed recipe URLs
                    data = resp.read()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{candidate}: {exc}")
                continue
            if sha256_bytes(data) != sha256:
                errors.append(f"{candidate}: sha256 {sha256_bytes(data)} != recipe {sha256}")
                continue
            cache.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
            return data, candidate
    raise RuntimeError("no verified download:\n  " + "\n  ".join(errors))


def _add(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size, info.mtime, info.mode = len(data), EPOCH, 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    tar.addfile(info, io.BytesIO(data))


def write_source_archive(prefix: Path, component: dict, out_dir: Path, cache: Path) -> dict:
    record = next(r for r in _records(prefix) if r.get("fn") == component["conda_package"]["fn"])
    pkg_dir = Path(record["extracted_package_dir"])
    stem = f"{component['name']}-{component['version']}-{component['build']}"
    members: dict[str, bytes] = {}
    fetched = []
    for src in component["upstream_sources"]:
        if "unresolved" in src:
            raise RuntimeError(f"{stem}: unresolved upstream source {src['unresolved']}")
        data, used = _fetch(src["urls"], src["sha256"], cache)
        members[f"{stem}/upstream/{src['fn']}"] = data
        fetched.append({"fn": src["fn"], "sha256": src["sha256"], "downloaded_from": used})
    for base, sub in ((pkg_dir / "info" / "recipe", "recipe"), (pkg_dir / "info" / "licenses", "licenses")):
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            members[f"{stem}/{sub}/{path.relative_to(base).as_posix()}"] = path.read_bytes()
    readme = (
        f"Corresponding source for {component['name']} {component['version']} (conda-forge build "
        f"{component['build']}) as bundled in Monograph PDF for macOS under engines/ocr.\n\n"
        f"Binary package: {component['conda_package']['url']}\n"
        f"Binary package SHA-256: {component['conda_package']['sha256']}\n"
        f"Feedstock: {component['feedstock']['url']} @ {component['feedstock']['commit']}\n"
        f"License: {component['license']}\n\n"
        "upstream/  release archive(s) named by the recipe, verified against the recipe's SHA-256\n"
        "recipe/    the complete rendered recipe the package was built from (patches, build scripts)\n"
        "licenses/  the package's license files\n"
    )
    members[f"{stem}/README.txt"] = readme.encode("utf-8")
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name in sorted(members):
            _add(tar, name, members[name])
    gz = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=gz, mtime=0, compresslevel=9) as f:
        f.write(raw.getvalue())
    archive = out_dir / f"{stem}.corresponding-source.tar.gz"
    archive.write_bytes(gz.getvalue())
    return {"archive": archive.name, "sha256": sha256_file(archive), "upstream": fetched,
            "verified_by": "upstream archive SHA-256 equals the hash in the package's own rendered recipe; "
                           "recipe and patches copied from the exact binary package"}


def build_sources(prefix: Path, inventory_path: Path, out_dir: Path, *, everything: bool = False) -> dict:
    """Corresponding source for copyleft components (required) or, with ``everything``, for all."""
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = Path(os.environ.get("MONOGRAPH_OCR_SOURCE_CACHE") or out_dir.parent / ".macos-ocr-source-cache")
    for component in inventory["components"]:
        if not (everything or component["copyleft"]):
            continue
        component["corresponding_source"] = write_source_archive(prefix, component, out_dir, cache)
        print(f"  {component['corresponding_source']['archive']}  {component['corresponding_source']['sha256']}")
    inventory_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    return inventory


# --------------------------------------------------------------------------- release check


def check(staged: Path, inventory_path: Path, sources_dir: Path | None) -> list[str]:
    """Every problem that must block a macOS release (empty list = pass)."""
    problems: list[str] = []
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    root = staged.parent.parent  # .../engines/ocr → bundle Resources (or a staging root)
    listed = set()
    for c in inventory.get("components", []):
        tag = f"{c.get('name')} {c.get('version')}"
        for rel, digest in c.get("binaries", {}).items():
            listed.add(rel)
            path = root / rel
            if not path.is_file():
                problems.append(f"{tag}: bundled file missing: {rel}")
            elif sha256_file(path) != digest:
                problems.append(f"{tag}: {rel} differs from the inventory (rebuild inventory and sources)")
        lic = root / c.get("license_dir", "")
        if not lic.is_dir() or not any(p.is_file() for p in lic.rglob("*")):
            problems.append(f"{tag}: license files missing in bundle ({c.get('license_dir')})")
        for patch, digest in c.get("patches", {}).items():
            if digest is None:
                problems.append(f"{tag}: recipe patch {patch} is not in the package recipe")
        for src in c.get("upstream_sources", []):
            if "unresolved" in src:
                problems.append(f"{tag}: upstream source not verifiable: {src['unresolved']}")
        cs = c.get("corresponding_source")
        if not cs:
            if c.get("copyleft"):
                problems.append(f"{tag}: copyleft component without a corresponding-source archive")
        elif sources_dir is not None:
            archive = sources_dir / cs["archive"]
            if not archive.is_file():
                problems.append(f"{tag}: corresponding-source archive missing: {cs['archive']}")
            elif sha256_file(archive) != cs["sha256"]:
                problems.append(f"{tag}: corresponding-source archive hash mismatch: {cs['archive']}")
    present = {f"engines/ocr/{p.relative_to(staged).as_posix()}" for top in ("bin", "lib")
               for p in (staged / top).rglob("*") if p.is_file()}
    for extra in sorted(present - listed):
        problems.append(f"bundled OCR file not in the inventory: {extra}")
    for name in ("TESSERACT_NOTICE.txt", "THIRD_PARTY_OCR.json"):
        if not (staged / name).is_file():
            problems.append(f"missing {name} in engines/ocr")
    return problems


def main(argv: list[str]) -> int:
    everything = "--all" in argv
    argv = [a for a in argv if a != "--all"]
    if len(argv) == 3 and argv[0] == "lock":
        count = write_lock(Path(argv[1]), Path(argv[2]))
        print(f"Locked {count} package(s) → {argv[2]}")
        return 0
    if len(argv) != 4 or argv[0] not in ("inventory", "sources", "check"):
        print(__doc__, file=sys.stderr)
        return 2
    cmd, a, b, c = argv[0], Path(argv[1]), Path(argv[2]), Path(argv[3])
    if cmd == "inventory":
        inventory = build_inventory(a, b)
        c.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
        print(f"Inventory: {len(inventory['components'])} package(s), all bundled files match their packages → {c}")
        return 0
    if cmd == "sources":
        build_sources(a, b, c, everything=everything)
        return 0
    problems = check(a, b, c if argv[3] else None)  # "" = bundle check only (no archives yet)
    for p in problems:
        print("ERROR:", p, file=sys.stderr)
    print("macOS OCR source/license check:", "FAIL" if problems else "PASS")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
