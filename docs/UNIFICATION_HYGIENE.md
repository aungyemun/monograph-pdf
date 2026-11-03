# Unification hygiene

## Recovery (created 2026-10-25)

| Ref | SHA |
| :--- | :--- |
| `backup/pre-unification-2026-10-25/main` | `4ef95e3b2420441d4a52aa42937f012e52d56a71` |
| `backup/pre-unification-2026-10-25/linux` | `bc5fa58167e3470ada0b1d653b70f31edfef376b` |
| `backup/pre-unification-2026-10-25/macos` | `0bae21d2d5fcf8384067d99b9586358b7ffd7518` |
| `backup/pre-unification-2026-10-25/release-v0.5.0` | `a45667fecf532026088b73e0a959278332320d69` |

Annotated tags: `backup-pre-unification-2026-10-25-{main,linux,macos,release-v0.5.0}`. These tags are
the recovery points; the `backup/pre-unification-2026-10-25/*` branches no longer exist on GitHub.

Offline bundle (outside repo): `%USERPROFILE%\MonographPDF-recovery\pre-unification-2026-10-25\`.

## Branches retained (reasons)

| Branch | Reason |
| :--- | :--- |
| `macos` | Legacy macOS 0.1.0 line; tip equals tag `v0.1.0-macos-1` |

## Branches retired

| Branch | Date | Kept as |
| :--- | :--- | :--- |
| `linux` | 2026-11-04 | Tag `backup-pre-unification-2026-10-25-linux` (`bc5fa58`); Linux now releases from `main` (v0.1.1-linux) |
| `release/v0.5.0` | 2026-11-04 | Merged into `main`; tags `v0.5.0` and `backup-pre-unification-2026-10-25-release-v0.5.0` (`a45667f`) |
| `feature/v0.3.0-secure-updates-diagnostics` | before 2026-11-04 | History on `main` ancestry |
| `backup/pre-unification-2026-10-25/*` | before 2026-11-04 | The annotated backup tags above |

Retiring a branch needs explicit maintainer approval and a tag (or `main` ancestry) that keeps its tip.
