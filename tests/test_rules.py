"""Band-edge + hysteresis tests for the SAANS rules engine.

Acceptance check for Task 2: `python -m pytest tests/test_rules.py -v` must be green.
Run offline — no network, no AWS.
"""

import os
import sys

import pytest

# allow running from repo root without install
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.rules import (  # noqa: E402
    ACTIONS,
    BANDS,
    TierState,
    aqi_to_band,
    aqi_to_tier,
    band_changed,
    initial_state,
    next_state,
)


class TestBandEdges:
    """The four CPCB band boundaries, plus 0."""

    @pytest.mark.parametrize("aqi,expected_tier", [
        (0, 0),
        (50, 0),
        (100, 0),
        (101, 1),      # good -> moderate
        (200, 1),
        (201, 2),      # moderate -> poor
        (300, 2),
        (301, 3),      # poor -> very_poor
        (400, 3),
        (401, 4),      # very_poor -> severe
        (500, 4),
    ])
    def test_edges(self, aqi, expected_tier):
        assert aqi_to_tier(aqi) == expected_tier

    def test_50_51_same_band(self):
        assert aqi_to_band(50) == aqi_to_band(51) == "good"

    def test_band_names(self):
        assert aqi_to_band(50) == "good"
        assert aqi_to_band(150) == "moderate"
        assert aqi_to_band(250) == "poor"
        assert aqi_to_band(350) == "very_poor"
        assert aqi_to_band(450) == "severe"

    def test_every_band_has_an_action(self):
        for _max, name in BANDS:
            assert name in ACTIONS, f"missing action for band {name}"

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            aqi_to_band(-1)


class TestInitialState:
    def test_first_reading_adopts_immediately(self):
        s = initial_state(250)
        assert s.tier == 2
        assert s.band == "poor"
        assert s.aqi == 250


class TestHysteresis:
    def test_upgrade_is_immediate(self):
        """AQI rising across a band must alert right away (safety)."""
        s = initial_state(50)          # good
        s2 = next_state(s, 150)        # moderate
        assert s2.tier == 1
        assert s2.prev_tier == 0

    def test_same_tier_refreshes(self):
        s = initial_state(250)         # poor
        s2 = next_state(s, 280)        # still poor
        assert s2.tier == 2
        assert s2.aqi == 280

    def test_downgrade_needs_two_readings(self):
        """AQI dropping one band must NOT flap on the first reading."""
        s = initial_state(250)         # poor (tier 2)
        s2 = next_state(s, 150)        # moderate (tier 1) - 1st sighting
        assert s2.tier == 2, "must hold poor on first downgrade sighting"
        assert s2.pending_tier == 1
        assert s2.pending_count == 1
        s3 = next_state(s2, 140)       # moderate - 2nd consecutive
        assert s3.tier == 1, "adopt downgrade only on 2nd consecutive reading"

    def test_downgrade_resets_if_it_rises_back(self):
        """Candidate downgrade is discarded if AQI rises back before confirming."""
        s = initial_state(250)         # poor
        s2 = next_state(s, 150)        # moderate candidate
        assert s2.tier == 2
        s3 = next_state(s2, 260)       # back up into poor
        assert s3.tier == 2
        assert s3.pending_tier is None
        s4 = next_state(s3, 150)       # moderate again -> must restart the count
        assert s4.tier == 2
        assert s4.pending_count == 1

    def test_two_band_drop_needs_two_readings(self):
        s = initial_state(450)         # severe (4)
        s2 = next_state(s, 250)        # poor (2), candidate
        assert s2.tier == 4
        s3 = next_state(s2, 250)       # confirm
        assert s3.tier == 2
        assert s3.prev_tier == 4


class TestBandChanged:
    def test_detects_transition(self):
        a = initial_state(50)
        b = next_state(a, 150)
        assert band_changed(a, b) is True

    def test_no_change_within_band(self):
        a = initial_state(250)
        b = next_state(a, 280)
        assert band_changed(a, b) is False

    def test_held_downgrade_is_not_a_change(self):
        """While hysteresis holds the tier, no alert should fire."""
        a = initial_state(250)
        b = next_state(a, 150)   # held at poor
        assert band_changed(a, b) is False
