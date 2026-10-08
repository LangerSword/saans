"""Seed tests — the demo data must actually support the demo.

Acceptance check for Task 2: `python -m pytest tests/test_seed.py -v` must be green.
Run offline — no network, no AWS.

The demo claim is "different schools, different tiers, same day". That only holds
if the schools read different stations. These tests make that a checked fact.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import seed  # noqa: E402

SUPPORTED_LANGUAGES = ("en", "hi", "te")


def test_schools_map_to_distinct_stations():
    """If two schools shared a station they would always read the same AQI,
    and the demo could never show a tier spread on one day."""
    stations = [s["station_id"] for s in seed.SCHOOLS]
    duplicates = {st for st in stations if stations.count(st) > 1}
    assert not duplicates, f"stations used by more than one school: {duplicates}"


def test_enough_schools_to_show_a_spread():
    assert len(seed.SCHOOLS) >= 3, "the demo needs at least three schools to show different tiers"


def test_every_school_points_at_a_known_station():
    known = set(seed.STATIONS)
    for s in seed.SCHOOLS:
        assert s["station_id"] in known, \
            f"{s['school_id']} points at unknown station {s['station_id']!r}"


def test_every_station_has_coordinates_in_delhi():
    """Coordinates outside Delhi would silently fetch the wrong city."""
    for sid, st in seed.STATIONS.items():
        assert 28.4 <= st["lat"] <= 28.9, f"{sid} lat {st['lat']} is outside Delhi"
        assert 76.8 <= st["lon"] <= 77.4, f"{sid} lon {st['lon']} is outside Delhi"


def test_stations_are_actually_spread_out():
    """Distinct stations must also be geographically distinct, or they read alike."""
    coords = [(st["lat"], st["lon"]) for st in seed.STATIONS.values()]
    closest = min(
        ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
        for i, a in enumerate(coords) for b in coords[i + 1:]
    )
    assert closest >= 0.05, f"two stations are only {closest:.3f} degrees apart — too close"


def test_school_ids_are_unique():
    ids = [s["school_id"] for s in seed.SCHOOLS]
    assert len(ids) == len(set(ids)), "duplicate school_id would collide on the partition key"


def test_principal_is_our_controlled_inbox():
    """Never point a seed at a real school: SNS email endpoints need a
    confirmation click, and an unconfirmed endpoint means a silent non-alert."""
    for s in seed.SCHOOLS:
        assert s.get("principal_email") == seed.DEMO_PRINCIPAL


def test_languages_are_supported():
    for s in seed.SCHOOLS:
        assert s["language"] in SUPPORTED_LANGUAGES, \
            f"{s['school_id']} has unsupported language {s['language']!r}"


def test_seed_record_shape():
    """The items written to saans-state must carry the keys the API reads."""
    for r in seed.seed_records():
        assert set(r) >= {"PK", "SK", "school_id", "name", "station_id",
                          "principal_email", "language"}
        assert r["PK"] == f"SCHOOL#{r['school_id']}"
        assert r["SK"] == "PROFILE"


def test_station_record_shape():
    for r in seed.station_records():
        assert set(r) >= {"PK", "SK", "station_id", "name", "lat", "lon"}
        assert r["PK"] == f"STATION#{r['station_id']}"
        assert r["SK"] == "META"


def test_state_is_not_seeded():
    """A school has no tier until its first reading. Seeding a STATE item would
    fake a tier the rules engine never set."""
    keys = {r["SK"] for r in seed.seed_records()}
    assert "STATE" not in keys, "the seed must not create STATE items — only saans-rules sets a tier"
