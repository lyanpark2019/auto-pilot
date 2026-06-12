"""Tests for scripts/_dogfood_noop.py — dogfood_identity smoke."""
from __future__ import annotations

from scripts._dogfood_noop import dogfood_identity


def test_identity_zero() -> None:
    assert dogfood_identity(0) == 0


def test_identity_positive() -> None:
    assert dogfood_identity(7) == 7


def test_identity_negative() -> None:
    assert dogfood_identity(-3) == -3
