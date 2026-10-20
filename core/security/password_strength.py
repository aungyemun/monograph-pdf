"""Offline password strength estimate for the Protect dialog.

A rough guide, not a guarantee: it rewards length and character variety and penalises patterns
that guessing tools try first (repeats, sequences, keyboard rows, very common passwords). Nothing
is sent anywhere and nothing is stored.
"""

from __future__ import annotations

import math
import string
from dataclasses import dataclass

_COMMON = {
    "password", "passw0rd", "123456", "12345678", "123456789", "1234567890", "qwerty", "qwertyuiop",
    "abc123", "111111", "000000", "letmein", "welcome", "admin", "iloveyou", "monkey", "dragon",
    "football", "baseball", "sunshine", "princess", "secret", "master", "login", "trustno1",
}
_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm", "1234567890", "abcdefghijklmnopqrstuvwxyz")
LABELS = ("Very weak", "Weak", "Fair", "Strong", "Very strong")


@dataclass(frozen=True)
class Strength:
    score: int  # 0..4
    label: str
    hint: str
    bits: float


def _pool(pw: str) -> int:
    pool = 0
    if any(c in string.ascii_lowercase for c in pw):
        pool += 26
    if any(c in string.ascii_uppercase for c in pw):
        pool += 26
    if any(c in string.digits for c in pw):
        pool += 10
    if any(c in string.punctuation or c == " " for c in pw):
        pool += 33
    if any(ord(c) > 127 for c in pw):
        pool += 100
    return max(pool, 1)


def _pattern_chars(pw: str) -> int:
    """Characters that belong to a run of 3+ repeats, sequences or keyboard-row neighbours."""
    low = pw.lower()
    flagged = [False] * len(low)
    for i in range(len(low) - 2):
        a, b, c = low[i : i + 3]
        same = a == b == c
        seq = ord(b) - ord(a) == ord(c) - ord(b) and abs(ord(b) - ord(a)) == 1
        row = any((a + b + c) in r or (c + b + a) in r for r in _ROWS)
        if same or seq or row:
            flagged[i] = flagged[i + 1] = flagged[i + 2] = True
    return sum(flagged)


def rate_password(pw: str) -> Strength:
    if not pw:
        return Strength(0, "", "", 0.0)
    if pw.lower() in _COMMON or pw.lower().rstrip("!1") in _COMMON:
        return Strength(0, LABELS[0], "This is one of the most common passwords.", 0.0)
    effective = len(pw) - _pattern_chars(pw) * 0.75
    bits = max(0.0, effective) * math.log2(_pool(pw))
    if len(set(pw)) <= 2:
        bits = min(bits, 10.0)
    score = 0 if bits < 28 else 1 if bits < 40 else 2 if bits < 60 else 3 if bits < 80 else 4
    if score <= 1 and len(pw) >= 12:
        hint = "Avoid repeats, sequences and keyboard patterns; a few unrelated words work well."
    elif score <= 1:
        hint = "Use 12 or more characters; a few unrelated words work well."
    elif score == 2:
        hint = "Longer is stronger: add another word or more characters."
    else:
        hint = ""
    return Strength(score, LABELS[score], hint, round(bits, 1))
