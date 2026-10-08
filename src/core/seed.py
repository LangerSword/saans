"""SAANS seed schools — mapped to DIFFERENT Delhi stations.

Why different stations: the demo needs to show different tiers on the same
day (e.g. one school in "moderate", another in "poor"), which only happens if
the schools read different stations, not one city-average.

Station coordinates are chosen to be spread across Delhi so that a single
day's modeled AQI differs between them. Values are demo data — replace with
real school records before any non-demo use.

principal_email MUST be an address WE control: SNS email endpoints require a
confirmation click before they deliver. Never point a seed at a real school.
"""

# Delhi-area points, spread out. (lat, lon) -> approximate area.
STATIONS = {
    "delhi-central":   {"name": "Central Delhi",   "lat": 28.6448, "lon": 77.2167},
    "delhi-east":      {"name": "East Delhi",      "lat": 28.6280, "lon": 77.2950},
    "delhi-west":      {"name": "West Delhi",      "lat": 28.6510, "lon": 77.0890},
    "delhi-north":     {"name": "North Delhi",     "lat": 28.7041, "lon": 77.1025},
    "delhi-south":     {"name": "South Delhi",     "lat": 28.5355, "lon": 77.2100},
}

# Principal inboxes we own for the demo (confirm the SNS subscription).
DEMO_PRINCIPAL = "saans-demo@langersword.in"

SCHOOLS = [
    {"school_id": "sch-001", "name": "DPS Mathura Road",        "station_id": "delhi-central", "language": "en", "principal_email": DEMO_PRINCIPAL},
    {"school_id": "sch-002", "name": "Govt. Sarvodaya Vidyalaya, Mayur Vihar", "station_id": "delhi-east", "language": "hi", "principal_email": DEMO_PRINCIPAL},
    {"school_id": "sch-003", "name": "Tagore International, Paschim Vihar", "station_id": "delhi-west", "language": "en", "principal_email": DEMO_PRINCIPAL},
    {"school_id": "sch-004", "name": "Kendriya Vidyalaya, Rohini", "station_id": "delhi-north", "language": "hi", "principal_email": DEMO_PRINCIPAL},
    {"school_id": "sch-005", "name": "Amity International, Saket", "station_id": "delhi-south", "language": "en", "principal_email": DEMO_PRINCIPAL},
]


def seed_records():
    """Yield the DynamoDB items for the seed, in single-table shape.

    One PROFILE item per school. STATE is created by the ingest/rules loop,
    not seeded (a school has no tier until its first reading).
    """
    for s in SCHOOLS:
        yield {
            "PK": f"SCHOOL#{s['school_id']}",
            "SK": "PROFILE",
            "school_id": s["school_id"],
            "name": s["name"],
            "station_id": s["station_id"],
            "principal_email": s["principal_email"],  # controlled inbox for the demo
            "language": s["language"],
        }


def station_records():
    """Yield STATION items so the dashboard/ingest can resolve coordinates."""
    for sid, st in STATIONS.items():
        yield {
            "PK": f"STATION#{sid}",
            "SK": "META",
            "station_id": sid,
            "name": st["name"],
            "lat": st["lat"],
            "lon": st["lon"],
        }


if __name__ == "__main__":
    import json
    recs = list(seed_records()) + list(station_records())
    print(json.dumps(recs, indent=2, ensure_ascii=False))
    print(f"\n# {len(SCHOOLS)} schools across {len(STATIONS)} stations", file=__import__('sys').stderr)
