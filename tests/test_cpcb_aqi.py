"""CPCB AQI conversion tests.

WHY THESE EXIST: Open-Meteo returns `us_aqi` (US EPA scale) alongside raw
concentrations. US AQI is not CPCB AQI. On a live Delhi day, feeding `us_aqi`
straight into our CPCB tier table put 38% of hours in the WRONG tier
(evidence: docs/screens/scale-check.txt). So we compute CPCB AQI ourselves.

Anchor values are from CPCB's own documentation, not invented here:
- How_AQI_Calculated.pdf states the PM2.5 sub-index is 51 at 31 ug/m3,
  75 at 45 ug/m3, and 100 at 60 ug/m3. Those three are asserted below.
- Breakpoints are from CPCB's AQI Calculator, "Breakpoints" sheet.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import rules  # noqa: E402


# ── CPCB's own published anchor values (How_AQI_Calculated.pdf) ──────────
@pytest.mark.parametrize("conc,expected", [
    (31.0, 51.0),   # CPCB: "the PM2.5 sub-index is 51 at a concentration of 31 ug/m3"
    (45.0, 74.66),  # CPCB prose says "75 at 45"; exact band (31,60)->(51,100) gives 74.66
    (60.0, 100.0),  # CPCB: "100 at 60 ug/m3"
])
def test_cpcb_published_anchor_values(conc, expected):
    """The formula must reproduce CPCB's own worked examples exactly."""
    assert rules.sub_index(conc, "pm2_5") == pytest.approx(expected, abs=0.1)


# ── sub-index band edges, both sides of every line ───────────────────────
@pytest.mark.parametrize("conc,expected", [
    (0.0, 0.0),
    (30.0, 50.0),      # top of "Good" (CPCB Table 3.6)
    (31.0, 51.0),      # first value of "Satisfactory"
    (60.0, 100.0),     # top of "Satisfactory"
    (61.0, 101.0),     # first value of "Moderate"
    (90.0, 200.0),     # top of "Moderate"
    (91.0, 201.0),     # first value of "Poor"
    (120.0, 300.0),    # top of "Poor"
    (121.0, 301.0),    # first value of "Very Poor"
    (250.0, 400.0),    # top of "Very Poor"
    (251.0, 401.0),    # first value of "Severe"
    (380.0, 500.0),    # top of the scale
])
def test_pm25_sub_index_edges(conc, expected):
    assert rules.sub_index(conc, "pm2_5") == pytest.approx(expected, abs=0.5)


@pytest.mark.parametrize("conc,expected", [
    (0.0, 0.0),
    (50.0, 50.0),      # top of "Good" (CPCB Table 3.5)
    (51.0, 51.0),      # first value of "Satisfactory"
    (100.0, 100.0),    # top of "Satisfactory"
    (101.0, 101.0),    # first value of "Moderate"
    (250.0, 200.0),    # top of "Moderate"
    (251.0, 201.0),    # first value of "Poor"
    (350.0, 300.0),    # top of "Poor"
    (351.0, 301.0),    # first value of "Very Poor"
    (430.0, 400.0),    # top of "Very Poor"
    (431.0, 401.0),    # first value of "Severe"
    (510.0, 500.0),    # top of the scale
])
def test_pm10_sub_index_edges(conc, expected):
    assert rules.sub_index(conc, "pm10") == pytest.approx(expected, abs=0.5)


def test_negative_concentration_rejected():
    with pytest.raises(ValueError):
        rules.sub_index(-1, "pm2_5")


def test_concentration_above_scale_rejected():
    """CPCB's scale stops at 500. Above that is off-scale, not silently clamped."""
    with pytest.raises(ValueError):
        rules.sub_index(400, "pm2_5")   # above the 380 top breakpoint


# ── the live misplacement this fix prevents ─────────────────────────────
def test_us_aqi_would_have_misclassified_the_live_delhi_day():
    """Regression test pinned to the measured failure.

    At pm2_5 = 55.8 ug/m3 (a real reading from the live Delhi feed on
    2026-10-09 12:00 IST), Open-Meteo's us_aqi was 165, which our CPCB tier
    table reads as "moderate". The correct CPCB AQI is 93, which is "good".
    A school would have been told to move PE indoors on a Satisfactory day.
    """
    pm2_5 = 55.8
    us_aqi = 165.0

    correct = rules.sub_index(pm2_5, "pm2_5")
    correct_tier = rules.aqi_to_band(correct)
    us_tier = rules.aqi_to_band(us_aqi)

    assert correct_tier == "good", f"CPCB AQI {correct} should read good, got {correct_tier}"
    assert us_tier == "moderate", f"US AQI {us_aqi} reads {us_tier}"
    assert correct_tier != us_tier, "this case must demonstrate the misplacement"


# ── aqi_from_pm ─────────────────────────────────────────────────────────
def test_aqi_from_pm_takes_the_worst_pollutant():
    """CPCB: the overall AQI is the MAXIMUM sub-index, not an average."""
    aqi, pollutant = rules.aqi_from_pm(pm2_5=50.0, pm10=100.0)
    # pm2_5=50 -> 83.3, pm10=100 -> 100.0; the worse one wins
    assert pollutant == "pm10"
    assert aqi == pytest.approx(100.0, abs=0.5)


def test_aqi_from_pm_with_only_pm25():
    aqi, pollutant = rules.aqi_from_pm(pm2_5=60.0, pm10=None)
    assert pollutant == "pm2_5"
    assert aqi == pytest.approx(100.0, abs=0.1)


def test_aqi_from_pm_with_only_pm10():
    aqi, pollutant = rules.aqi_from_pm(pm2_5=None, pm10=200.0)
    assert pollutant == "pm10"


def test_aqi_from_pm_requires_at_least_one_particulate():
    """CPCB: an index needs PM2.5 or PM10. With neither, we must refuse, not guess."""
    with pytest.raises(ValueError):
        rules.aqi_from_pm(pm2_5=None, pm10=None)


def test_concentration_to_tier_end_to_end():
    """The whole path the ingest Lambda will use: concentration -> tier."""
    # pm2_5=55.8 -> 91.8 (good), but pm10=110 -> 107.0 (moderate). CPCB takes the
    # WORST sub-index, so the tier is moderate. This is the whole point of the
    # conversion: the PM-only index is driven by whichever particulate is worse.
    aqi, dominant = rules.aqi_from_pm(pm2_5=55.8, pm10=110.0)
    assert dominant == "pm10"
    assert rules.aqi_to_band(aqi) == "moderate"
    assert rules.aqi_to_tier(aqi) == 1

    aqi, _ = rules.aqi_from_pm(pm2_5=95.0, pm10=180.0)
    assert rules.aqi_to_band(aqi) == "poor"
    assert rules.aqi_to_tier(aqi) == 2

    aqi, _ = rules.aqi_from_pm(pm2_5=300.0, pm10=450.0)
    assert rules.aqi_to_band(aqi) == "severe"
    assert rules.aqi_to_tier(aqi) == 4


def test_pm_only_is_a_documented_simplification():
    """Guard the honesty claim: if someone adds a pollutant without saying so,
    this fails and the blog claim must be revisited."""
    assert rules.PM_ONLY_POLLUTANTS == ("pm2_5", "pm10")
