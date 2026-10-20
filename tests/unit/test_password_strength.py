"""Offline password strength estimate shown in Protect with Password."""

from __future__ import annotations

import pytest

from core.security.password_strength import rate_password


@pytest.mark.parametrize("pw", ["password", "123456", "qwerty", "Password1", "aaaaaaaaaaaaaaaa", "abcdefghijkl",
                                "qwertyuiop12"])
def test_common_and_patterned_passwords_are_weak(pw):
    assert rate_password(pw).score <= 1


@pytest.mark.parametrize("pw", ["correct horse battery staple", "Zx9!kQ2#pL7@vR", "plum-ladder-ocean-91"])
def test_long_varied_passwords_are_strong(pw):
    assert rate_password(pw).score >= 3


def test_empty_has_no_rating_and_scores_grow_with_length():
    assert rate_password("").label == ""
    scores = [rate_password("k7#Rw" * n).score for n in (1, 2, 3)]
    assert scores == sorted(scores) and scores[0] < scores[-1]


def test_weak_rating_explains_how_to_improve():
    assert rate_password("cat").hint
    assert rate_password("abcdefghijkl").hint.startswith("Avoid")
