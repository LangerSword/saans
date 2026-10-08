"""Advisory honesty tests: the estimate disclaimer and stated limits.

These exist so the advisory can never be generated that reads as a measured
fact. The data is modeled at ~11 km and the index is PM-only; the disclaimer is
mandatory, not optional.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import rules  # noqa: E402


def test_every_advisory_carries_the_estimate_disclaimer():
    """No band may produce an advisory without the estimate disclaimer."""
    for band in rules.ACTIONS:
        text = rules.advisory_text(band)
        assert rules.ESTIMATE_DISCLAIMER in text, f"band {band!r} advisory lacks the disclaimer"


def test_disclaimer_says_it_is_an_estimate_not_a_measurement():
    d = rules.ESTIMATE_DISCLAIMER
    assert "estimate" in d.lower()
    assert "not a measurement" in d.lower()


def test_disclaimer_tells_principal_to_use_judgment():
    assert "judgment" in rules.ESTIMATE_DISCLAIMER.lower()
    assert "local reading" in rules.ESTIMATE_DISCLAIMER.lower()


def test_stated_limits_name_the_pm_only_and_modeled_limits():
    limits = rules.STATED_LIMITS
    assert "PM-only" in limits["index"]
    assert "modeled" in limits["data"]
    assert "11 km" in limits["data"]
    assert limits["residual_misclassification_pct"] == 12


def test_advisory_text_is_a_single_readable_string():
    text = rules.advisory_text("poor")
    assert isinstance(text, str)
    assert len(text) > len(rules.ACTIONS["poor"])
    # the disclaimer is appended, not replacing the action
    assert text.startswith(rules.ACTIONS["poor"])


def test_unknown_band_falls_back_to_moderate_with_disclaimer():
    text = rules.advisory_text("not_a_real_band")
    assert rules.ACTIONS["moderate"] in text
    assert rules.ESTIMATE_DISCLAIMER in text
