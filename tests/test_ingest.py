"""Task 3 ingest tests: provenance, null handling, staleness, snapshot.

Run offline — no network. The snapshot fixture stands in for the live feed and is
labeled as modeled data.
"""
import json
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import ingest, rules  # noqa: E402

SNAPSHOT = os.path.join(os.path.dirname(__file__), "..", "fixtures", "open-meteo-snapshot.json")


def load_snapshot():
    with open(SNAPSHOT, encoding="utf-8") as f:
        return json.load(f)


# ── provenance ───────────────────────────────────────────────────────────
def test_every_reading_carries_provenance():
    payload = load_snapshot()
    readings = ingest.parse_open_meteo(payload, "sch-001")
    assert readings, "snapshot should yield readings"
    for r in readings:
        assert r.source == "open-meteo-cams"
        assert r.modeled is True
        assert r.breakpoint_version == "cpcb-naqi-2014-pm-v1"
        assert r.school_id == "sch-001"
        assert r.timestamp_utc


def test_reading_round_trips_through_json():
    r = ingest.Reading("sch-001", "2026-10-09T03:00", 80.0, 130.0,
                       "open-meteo-cams", True, "cpcb-naqi-2014-pm-v1")
    back = ingest.Reading.from_json(r.to_json())
    assert back == r


def test_attribution_is_present_and_names_cams():
    assert "Open-Meteo" in ingest.ATTRIBUTION
    assert "CAMS" in ingest.ATTRIBUTION
    assert "CC-BY" in ingest.ATTRIBUTION
    assert "not a station measurement" in ingest.ATTRIBUTION.lower()


# ── null handling (the safety-critical one) ──────────────────────────────
def test_null_particulate_is_kept_as_none_not_zero():
    """A null must stay None. A coerced 0 would read as Good air."""
    payload = load_snapshot()
    readings = ingest.parse_open_meteo(payload, "sch-001")
    by_ts = {r.timestamp_utc: r for r in readings}
    # hours 03 and 04 have null pm2_5 in the fixture
    assert by_ts["2026-10-09T03:00"].pm2_5 is None
    assert by_ts["2026-10-09T04:00"].pm2_5 is None


def test_null_particulate_still_computes_from_the_other():
    """With pm2_5 null but pm10 present, we still get a usable AQI from pm10."""
    payload = load_snapshot()
    readings = ingest.parse_open_meteo(payload, "sch-001")
    r = {x.timestamp_utc: x for x in readings}["2026-10-09T03:00"]
    aqi, dominant = rules.aqi_from_pm(r.pm2_5, r.pm10)
    assert dominant == "pm10"
    assert aqi > 0  # a real index, not a fake-zero


def test_all_null_hour_is_dropped_not_zeroed():
    """A reading with no particulates carries no info; it must be dropped."""
    payload = load_snapshot()
    readings = ingest.parse_open_meteo(payload, "sch-001")
    times = {r.timestamp_utc for r in readings}
    assert "2026-10-09T22:00" not in times  # all-null in the fixture
    assert "2026-10-09T23:00" not in times


def test_a_null_never_produces_a_good_tier_by_accident():
    """Regression: coercing null->0 would give AQI 0 / 'good'. It must not."""
    payload = load_snapshot()
    readings = ingest.parse_open_meteo(payload, "sch-001")
    r = {x.timestamp_utc: x for x in readings}["2026-10-09T03:00"]
    # if a null had become 0, the pm2_5 sub-index would be 0 and could win the
    # max() and drag the AQI down. Assert the AQI reflects the real pm10 value.
    aqi, dominant = rules.aqi_from_pm(r.pm2_5, r.pm10)
    assert aqi > 100, "a null hour must not collapse to a Good/zero AQI"
    assert dominant == "pm10"


# ── staleness ────────────────────────────────────────────────────────────
def make_reading(hours_ago):
    ts = datetime.now(timezone.utc)
    from datetime import timedelta
    ts = ts - timedelta(hours=hours_ago)
    return ingest.Reading("sch-001", ts.isoformat(), 200.0, 300.0,
                          "open-meteo-cams", True, "cpcb-naqi-2014-pm-v1")


def test_fresh_reading_is_not_stale():
    assert ingest.is_stale(make_reading(1)) is False


def test_old_reading_is_stale():
    assert ingest.is_stale(make_reading(5)) is True


def test_staleness_threshold_is_shared():
    """ingest and rules must agree on the threshold, or the gate is unsound."""
    assert ingest.STALE_AFTER_HOURS == rules.STALE_AFTER_HOURS


def test_stale_reading_refuses_to_downgrade():
    """The safety rule: stale data must not relax a tier."""
    state = rules.initial_state(300.0)   # poor, tier 2
    assert state.tier == 2
    # a stale reading showing good air
    fresh_good = rules.next_state_safe(state, 30.0, stale=True)
    assert fresh_good.tier == 2, "stale data must not downgrade the tier"
    # the same reading, when fresh, is held by hysteresis (first sight) anyway,
    # but a second fresh reading would adopt it — the stale path never gets there
    assert rules.next_state_safe(state, 30.0, stale=False).tier in (1, 2)


def test_stale_reading_still_allows_upgrade():
    """More caution is always safe to add, even on old data."""
    state = rules.initial_state(50.0)    # good, tier 0
    worse = rules.next_state_safe(state, 300.0, stale=True)
    assert worse.tier == 2, "a stale reading may still escalate for safety"


def test_stale_same_tier_refreshes():
    state = rules.initial_state(150.0)   # moderate
    refreshed = rules.next_state_safe(state, 160.0, stale=True)
    assert refreshed.tier == state.tier
    assert refreshed.aqi == 160.0


# ── snapshot fallback ────────────────────────────────────────────────────
def test_snapshot_is_labeled_as_modeled():
    payload = load_snapshot()
    assert payload["_modeled"] is True
    assert payload["_source"] == "open-meteo-cams"
    assert "not a station measurement" in payload["_README"].lower()


def test_snapshot_parses_into_readings():
    payload = load_snapshot()
    readings = ingest.parse_open_meteo(payload, "sch-001", source="snapshot-fixture")
    # snapshot-fixture is also modeled per DATA_NATURE
    assert readings
    assert all(r.modeled is True for r in readings)


def test_latest_reading_handles_empty():
    assert ingest.latest_reading([]) is None


def test_latest_reading_picks_newest():
    readings = ingest.parse_open_meteo(load_snapshot(), "sch-001")
    newest = ingest.latest_reading(readings)
    assert newest is not None
    assert newest.timestamp_utc == max(r.timestamp_utc for r in readings)


# ── fetch with injected opener (no network) ──────────────────────────────
def test_fetch_reading_uses_injected_opener():
    """The network seam: tests inject a stub, never the wire."""
    payload = json.dumps(load_snapshot())
    readings = ingest.fetch_reading("sch-001", 28.6, 77.2, opener=lambda url: payload)
    assert readings
    assert all(r.source == "open-meteo-cams" for r in readings)
