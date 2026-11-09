"""Read-only privacy and secrets scan for the repository, builds and release files.

    python scripts/audit/privacy_scan.py [--git REPO ...] [--path FILE_OR_DIR_OR_ZIP ...]
                                         [--patterns FILE] [--out REPORT.json] [--show-context]

What is scanned
  --git   every blob in the object database (all branches, tags, stashes and unreachable objects),
          every commit message and author/committer identity, and .git/config, packed-refs,
          FETCH_HEAD, ORIG_HEAD. A flagged blob is reported with its paths and whether a
          remote-tracking branch or a tag already contains it (= probably public).
  --path  files, folders (recursively; .git, env, packages and junctions are skipped) and .zip
          archives (every entry, one level of nested zips). Binary files are scanned as bytes.

What is looked for
  * secret-shaped strings: GitHub, AWS, Google, OpenAI/Anthropic and Slack tokens, private-key
    blocks, minisign secret keys, Bearer tokens, URLs with embedded credentials, password / API
    key assignments with a literal value;
  * personal text: each line of the patterns file is one fixed string (case-insensitive), for
    example your private e-mail address, Windows user folder, computer name or the number of a
    private document. Default file: <first --git repo>/.git/info/private-patterns.txt, which is
    local to your clone and never committed or pushed;
  * e-mail addresses other than GitHub no-reply and example.* addresses;
  * commits with AI attribution (co-author trailers, "Generated with", session links).

Nothing is changed. Matches are never printed in full: secrets are masked, personal patterns are
reported by their line number in the patterns file only (unless --show-context is given, and
even then the context is written only to the JSON report). Exit code 1 when a secret, a personal
pattern, a remote URL with credentials or AI attribution is found; other e-mail addresses are
listed for review only.
Expect findings in test files that contain deliberately fake secrets; review each one.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

SECRET = {
    "github_token": rb"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}",
    "github_pat": rb"github_pat_[A-Za-z0-9_]{40,}",
    "aws_access_key": rb"\bAKIA[0-9A-Z]{16}\b",
    "private_key_block": rb"-----BEGIN [A-Z ]{0,20}PRIVATE KEY-----",
    "minisign_secret": rb"untrusted comment: [^\n]{0,60}secret[ ]key",
    "slack_token": rb"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    "google_api_key": rb"\bAIza[0-9A-Za-z_\-]{35}\b",
    "openai_anthropic_key": rb"\bsk-(?:ant-)?[A-Za-z0-9_\-]{24,}",
    "bearer_token": rb"Bearer\s+[A-Za-z0-9._\-]{24,}",
    "credential_url": rb"https?://[^/\s:@'\"<>]{1,64}:[^/\s@'\"<>]{1,128}@[A-Za-z0-9.\-]+",
    "password_assignment": rb"(?i)\b(?:password|passwd|pwd|passphrase)\s*[:=]\s*['\"][^'\"\s]{6,}['\"]",
    "secret_assignment": (rb"(?i)\b(?:api[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token|secret[_-]?key)"
                          rb"\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"),
}
EMAIL = re.compile(rb"[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9\-]{1,63}(?:\.[A-Za-z0-9\-]{1,63})*\.[A-Za-z]{2,12}")
EMAIL_OK = re.compile(rb"(?i)@users\.noreply\.github\.com$|^noreply@|no-reply|@example\.(?:com|org|net)$|\.invalid$|\.test$")
NOT_EMAIL_SUFFIX = (b".png", b".jpg", b".svg", b".py", b".dll", b".ico", b".gif")
AI_ATTRIBUTION = re.compile(r"(?i)co-authored-by:.*(claude|anthropic|cursor|copilot|openai|chatgpt|gpt|gemini)|"
                            r"generated (with|by) .*(claude|cursor|copilot|\bai\b)|claude\.ai/code|claude-session:")
MAX_BYTES = 64 * 2**20
SKIP_DIRS = {".git", "env", ".venv", "packages", "__pycache__", "node_modules"}


def load_patterns(path: Path | None) -> list[bytes]:
    if path is None or not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s.encode("utf-8"))
    return out


class Scanner:
    def __init__(self, personal: list[bytes], show_context: bool = False) -> None:
        self.secret = {k: re.compile(v) for k, v in SECRET.items()}
        # fixed strings, case-insensitive; reported by line number, never by value
        self.personal = [(i + 1, re.compile(re.escape(p), re.IGNORECASE)) for i, p in enumerate(personal)]
        self.show_context = show_context
        self.findings: dict[str, list[dict]] = defaultdict(list)
        self.emails: dict[str, set[str]] = defaultdict(set)
        self.stats = {"files": 0, "zip_entries": 0, "git_blobs": 0, "skipped_large": [], "unreadable": []}

    @staticmethod
    def mask(raw: bytes) -> str:
        s = raw.decode("utf-8", "replace")
        return s[:4] + "..." + f"[{len(s)} chars]"

    @staticmethod
    def mask_email(raw: bytes) -> str:
        local, _, domain = raw.decode("utf-8", "replace").partition("@")
        return (local[:2] + "...@" + domain).lower()

    def _context(self, data: bytes, a: int, b: int) -> str:
        return data[max(0, a - 40):min(len(data), b + 40)].decode("utf-8", "replace").replace("\n", "⏎")[:160]

    def scan_bytes(self, data: bytes, where: str) -> set[str]:
        kinds: set[str] = set()
        for name, rx in self.secret.items():
            for m in rx.finditer(data):
                self.findings[name].append({"where": where, "match": self.mask(m.group(0))})
                kinds.add(name)
        for line_no, rx in self.personal:
            for m in rx.finditer(data):
                rec = {"where": where, "pattern_line": line_no}
                if self.show_context:
                    rec["context"] = self._context(data, m.start(), m.end())
                self.findings["personal_pattern"].append(rec)
                kinds.add("personal_pattern")
        for m in EMAIL.finditer(data):
            e = m.group(0)
            if not EMAIL_OK.search(e) and not e.lower().endswith(NOT_EMAIL_SUFFIX):
                self.emails[self.mask_email(e)].add(where)
        return kinds

    # -- files, folders, zips --------------------------------------------------------------------
    def scan_path(self, p: Path) -> None:
        if p.is_symlink():
            return
        if p.is_dir():
            for root, dirs, files in os.walk(p, followlinks=False):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not _is_link(os.path.join(root, d))]
                for f in files:
                    self.scan_path(Path(root, f))
            return
        try:
            size = p.stat().st_size
        except OSError as exc:
            self.stats["unreadable"].append(f"{p}: {exc}")
            return
        if p.suffix.lower() == ".zip":
            self._scan_zip(p)
            return
        if size > MAX_BYTES:
            self.stats["skipped_large"].append(str(p))
            return
        try:
            data = p.read_bytes()
        except OSError as exc:
            self.stats["unreadable"].append(f"{p}: {exc}")
            return
        self.stats["files"] += 1
        self.scan_bytes(data, str(p))

    def _scan_zip(self, p: Path) -> None:
        try:
            with zipfile.ZipFile(p) as z:
                for info in z.infolist():
                    if info.is_dir() or info.file_size > MAX_BYTES:
                        continue
                    data = z.read(info)
                    self.stats["zip_entries"] += 1
                    self.scan_bytes(data, f"{p}!{info.filename}")
                    if info.filename.lower().endswith(".zip"):
                        with zipfile.ZipFile(io.BytesIO(data)) as inner:
                            for ii in inner.infolist():
                                if not ii.is_dir() and ii.file_size <= MAX_BYTES:
                                    self.stats["zip_entries"] += 1
                                    self.scan_bytes(inner.read(ii), f"{p}!{info.filename}!{ii.filename}")
        except (zipfile.BadZipFile, OSError) as exc:
            self.stats["unreadable"].append(f"{p}: {exc}")

    # -- git -------------------------------------------------------------------------------------
    def scan_git(self, repo: Path) -> dict:
        info: dict = {"repo": str(repo), "remotes": []}
        for line in _git(repo, "remote", "-v").decode("utf-8", "replace").splitlines():
            parts = line.split()
            url = parts[1] if len(parts) > 1 else ""
            info["remotes"].append({"name": parts[0] if parts else "", "url": re.sub(r"//[^@/]+@", "//***@", url),
                                    "has_credentials": bool(re.search(r"//[^/@]+@", url))})
        gitdir = Path(_git(repo, "rev-parse", "--absolute-git-dir").decode().strip())
        for extra in ("config", "FETCH_HEAD", "ORIG_HEAD", "packed-refs"):
            f = gitdir / extra
            if f.is_file():
                self.scan_bytes(f.read_bytes(), f"{repo}:.git/{extra}")
        listing = _git(repo, "cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype) %(objectsize)")
        blobs = []
        for row in listing.decode().splitlines():
            sha, kind, size = row.split()
            if kind == "blob":
                if int(size) <= MAX_BYTES:
                    blobs.append(sha)
                else:
                    self.stats["skipped_large"].append(f"{repo}:blob:{sha}")
        flagged: dict[str, set[str]] = {}
        proc = subprocess.Popen(["git", "-C", str(repo), "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        assert proc.stdin and proc.stdout
        for sha in blobs:
            proc.stdin.write(sha.encode() + b"\n")
            proc.stdin.flush()
            size = int(proc.stdout.readline().split()[2])
            data = proc.stdout.read(size)
            proc.stdout.read(1)
            kinds = self.scan_bytes(data, f"blob:{sha}")
            if kinds:
                flagged[sha] = kinds
        proc.stdin.close()
        proc.wait()
        self.stats["git_blobs"] += len(blobs)
        paths: dict[str, set[str]] = defaultdict(set)
        if flagged:
            raw = _git(repo, "log", "--all", "--format=", "--raw", "--no-abbrev", "-m").decode("utf-8", "replace")
            for line in raw.splitlines():
                if line.startswith(":") and "\t" in line:
                    meta, _, path = line.partition("\t")
                    cols = meta.split()
                    if len(cols) >= 4 and cols[3] in flagged:
                        paths[cols[3]].add(path.split("\t")[-1])
        public_refs = _git(repo, "for-each-ref", "--format=%(refname)", "refs/remotes", "refs/tags").decode().split()
        public: set[str] = set()
        if flagged and public_refs:
            objs = _git(repo, "rev-list", "--objects", *public_refs).decode("utf-8", "replace")
            public = {ln.split()[0] for ln in objs.splitlines() if ln.split()[0] in flagged}
        info["flagged_blobs"] = {sha: {"kinds": sorted(k), "paths": sorted(paths.get(sha, ())),
                                       "in_remote_branch_or_tag": sha in public} for sha, k in flagged.items()}
        log = _git(repo, "log", "--all", "--format=%H%x1f%ae%x1f%ce%x1f%B%x1e").decode("utf-8", "replace")
        identities: dict[str, int] = defaultdict(int)
        attribution = []
        for rec in log.split("\x1e"):
            f = rec.strip("\n").split("\x1f")
            if len(f) < 4:
                continue
            for e in (f[1], f[2]):
                identities["ok" if EMAIL_OK.search(e.encode()) else self.mask_email(e.encode())] += 1
            self.scan_bytes(f[3].encode("utf-8"), f"commit-message:{f[0][:10]}")
            if AI_ATTRIBUTION.search(f[3]):
                attribution.append(f[0][:10])
        info["commit_email_counts"] = dict(identities)
        info["commits_with_ai_attribution"] = attribution
        return info


def _is_link(path: str) -> bool:
    if os.path.islink(path):
        return True
    try:  # Windows junction / reparse point
        return bool(getattr(os.lstat(path), "st_file_attributes", 0) & 0x400)
    except OSError:
        return False


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--git", action="append", default=[], type=Path, help="repository to scan (repeatable)")
    ap.add_argument("--path", action="append", default=[], type=Path, help="file, folder or zip (repeatable)")
    ap.add_argument("--patterns", type=Path, help="personal fixed strings, one per line "
                                                   "(default: <first --git repo>/.git/info/private-patterns.txt)")
    ap.add_argument("--out", type=Path, help="write the full JSON report here (keep it private)")
    ap.add_argument("--show-context", action="store_true", help="put text around personal matches into the JSON report")
    a = ap.parse_args(argv)
    if not a.git and not a.path:
        ap.error("give at least one --git or --path")
    patterns_file = a.patterns
    if patterns_file is None and a.git:
        gd = _git(a.git[0], "rev-parse", "--absolute-git-dir").decode().strip()
        patterns_file = Path(gd) / "info" / "private-patterns.txt"
    personal = load_patterns(patterns_file)
    s = Scanner(personal, a.show_context)
    repos = [s.scan_git(r) for r in a.git]
    for p in a.path:
        s.scan_path(p)
    summary = {k: len(v) for k, v in sorted(s.findings.items())}
    report = {"stats": s.stats, "personal_patterns_loaded": len(personal), "summary": summary, "repos": repos,
              "findings": dict(s.findings), "other_emails": {e: sorted(w)[:5] for e, w in sorted(s.emails.items())}}
    if a.out:
        a.out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"personal patterns loaded: {len(personal)}"
          + ("" if personal else "  (none: create .git/info/private-patterns.txt, see docs/PRIVACY_RELEASE_CHECK.md)"))
    print("scanned:", json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in s.stats.items()}))
    print("findings:", json.dumps(summary) if summary else "none")
    for kind, recs in sorted(s.findings.items()):
        places = [r for r in recs if not r["where"].startswith("blob:")]
        for r in places[:5]:
            what = r.get("match") or f"pattern line {r.get('pattern_line')}"
            print(f"  {kind}: {r['where']}  ({what})")
        if len(places) > 5:
            print(f"  {kind}: ... {len(places) - 5} more places (see --out report)")
    print("other e-mail addresses:", ", ".join(sorted(s.emails)) or "none")
    for r in repos:
        flagged = r["flagged_blobs"]
        public = sum(1 for v in flagged.values() if v["in_remote_branch_or_tag"])
        print(f"{r['repo']}: blobs flagged {len(flagged)} (already in a remote branch or tag: {public}); "
              f"remote URLs with credentials: {sum(x['has_credentials'] for x in r['remotes'])}; "
              f"commits with AI attribution: {len(r['commits_with_ai_attribution'])}; "
              f"commit e-mails: {r['commit_email_counts']}")
        for sha, v in sorted(flagged.items(), key=lambda kv: kv[1]["paths"]):
            print(f"  {sha[:10]} {','.join(v['kinds'])} {'PUBLIC ' if v['in_remote_branch_or_tag'] else ''}"
                  f"{'; '.join(v['paths'][:3]) or '(path unknown)'}")
    found = bool(summary) or any(r["commits_with_ai_attribution"] or any(x["has_credentials"] for x in r["remotes"])
                                 for r in repos)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
