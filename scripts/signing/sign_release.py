"""Release signing command line (docs/CODE_SIGNING_POLICY.md). Nothing is ever signed by default.

    python scripts/signing/sign_release.py approve --version X.Y.Z --approver "Name"
           (asks for the typed confirmation "SIGN MONOGRAPH PDF X.Y.Z"; Signing Approver only)
    python scripts/signing/sign_release.py check-approval --version X.Y.Z
    python scripts/signing/sign_release.py sign --provider {none,signtool,signpath} --version X.Y.Z
           [--production] [--dry-run] FILE...
    python scripts/signing/sign_release.py status FILE...      (Authenticode status of each file)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import signing  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("approve")
    a1.add_argument("--version", required=True)
    a1.add_argument("--approver", required=True)
    a1.add_argument("--confirm", help="the confirmation phrase (otherwise asked interactively)")
    a2 = sub.add_parser("check-approval")
    a2.add_argument("--version", required=True)
    a3 = sub.add_parser("sign")
    a3.add_argument("--provider", choices=signing.PROVIDERS, default="none")
    a3.add_argument("--version", required=True)
    a3.add_argument("--production", action="store_true")
    a3.add_argument("--dry-run", action="store_true")
    a3.add_argument("files", nargs="*", type=Path)
    a4 = sub.add_parser("status")
    a4.add_argument("files", nargs="+", type=Path)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "approve":
            phrase = signing.confirmation_phrase(a.version)
            confirm = a.confirm
            if confirm is None:
                if not sys.stdin.isatty():
                    raise signing.SigningError("approval needs an interactive confirmation (or --confirm)")
                confirm = input(f'Approve production signing of {signing.PRODUCT_NAME} {a.version} at HEAD?\n'
                                f'Type "{phrase}" to approve: ').strip()
            path = signing.create_approval(a.version, a.approver, confirm)
            print(f"approval recorded: {path}")
        elif a.cmd == "check-approval":
            rec = signing.check_approval(a.version)
            print(f"approved by {rec['approver']} at {rec['approved_at']} for commit {rec['commit']}")
        elif a.cmd == "sign":
            res = signing.sign_files(a.provider, a.version, list(a.files), production=a.production, dry_run=a.dry_run)
            for f in res.signed:
                print(f"signed    {f}")
            for f in res.unsigned:
                print(f"unsigned  {f}")
            for c in res.commands if a.dry_run else []:
                print("would run: " + " ".join(c))
        else:
            for f in a.files:
                print(f"{signing.authenticode_status(f):12} {f}")
    except signing.SigningError as exc:
        print(f"signing: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
