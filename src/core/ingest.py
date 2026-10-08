"""Task 3 — ingest: provenance, null handling, staleness, snapshot fallback.

Pure, offline-testable. No network at import. The network fetch lives in
`fetch_reading`, which takes an injected opener so tests never touch the wire.

Every reading carries its provenance, so the blog can trace any number back to
its inputs. A null from the feed means "no reading", never zero — a zero would
read as Good air and tell a school it was safe when we simply had no data.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

# ── provenance ───────────────────────────────────────────────────────────
# The version tag lets us trace a computed AQI back to the exact breakpoint
# table used. Bump it whenever CPCB_BREAKPOINTS changes, and the blog can cite it.
BREAKPOINT_TABLE_VERSION = "cpcb-naqi-2014-pm-v1"

# Source label. Stored on every reading so the dashboard and blog can say
# "modeled" out loud instead of implying station measurements.
SOURCE_OPEN_METEO = "open-meteo-cams"
SOURCE_SNAPSHOT = "snapshot-fixture"
SOURCE_MANUAL = "manual"

# What the data actually is, stated plainly for the advisory and the dashboard.
DATA_NATURE = {
    SOURCE_OPEN_METEO: "modeled",   # CAMS grid model, ~11 km, NOT a station monitor
    SOURCE_SNAPSHOT: "modeled",     # captured from the same modeled feed
    SOURCE_MANUAL: "measured",      # a human entered a station value
}

# Open-Meteo attribution (required by CC-BY 4.0; free tier is non-commercial).
# Shown on the dashboard and cited in the blog.
ATTRIBUTION = (
    "Air quality data: Open-Meteo.com, from the Copernicus Atmosphere Monitoring "
    "Service (CAMS) ensemble. Modeled forecast, not a station measurement. "
    "Licensed CC-BY 4.0."
)

# Staleness: if the newest reading is older than this, treat it as stale and
# refuse to downgrade a tier on it. Failing toward caution for a school tool.
STALE_AFTER_HOURS = 3


@dataclass(frozen=True)
class Reading:
    """One air-quality reading, with everything needed to trace it."""
    school_id: str
    timestamp_utc: str            # ISO-8601, the reading's own time
    pm2_5: Optional[float]        # ug/m3, None = no reading (NOT zero)
    pm10: Optional[float]         # ug/m3, None = no reading (NOT zero)
    source: str                   # SOURCE_* above
    modeled: bool                 # True for CAMS model output
    breakpoint_version: str       # which CPCB table the AQI will be computed from

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @staticmethod
    def from_json(s: str) -> "Reading":
        return Reading(**json.loads(s))


def is_stale(reading: Reading, now: Optional[datetime] = None) -> bool:
    """True if the reading is older than STALE_AFTER_HOURS.

    A school-safety tool must fail toward caution: a stale reading must not be
    used to DOWNGRADE a tier (it could be based on air that has since worsened).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    ts = datetime.fromisoformat(reading.timestamp_utc.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_hours = (now - ts).total_seconds() / 3600.0
    return age_hours > STALE_AFTER_HOURS


def parse_open_meteo(payload: dict, school_id: str,
                     source: str = SOURCE_OPEN_METEO) -> list[Reading]:
    """Turn an Open-Meteo hourly response into Reading objects.

    NULL HANDLING: the feed returns null for hours it has no value for. A null
    means "no reading" and is kept as None. It is NEVER coerced to 0, because a
    0 ug/m3 would compute as AQI 0 ("Good") and a school would be told the air
    was fine when we simply had no data. A reading with BOTH particulates null
    is dropped entirely — it carries no information.

    Hours where only one particulate is missing are kept: the rules engine's
    aqi_from_pm() computes from whichever pollutant is present and records which
    one dominated, so a partial reading is still usable and still traceable.
    """
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    pm25 = hourly.get("pm2_5") or []
    pm10 = hourly.get("pm10") or []
    modeled = DATA_NATURE.get(source) == "modeled"

    readings = []
    for i, ts in enumerate(times):
        p25 = pm25[i] if i < len(pm25) else None
        p10 = pm10[i] if i < len(pm10) else None
        if p25 is None and p10 is None:
            continue  # no information; drop rather than fake a zero
        readings.append(Reading(
            school_id=school_id,
            timestamp_utc=ts,
            pm2_5=p25,
            pm10=p10,
            source=source,
            modeled=modeled,
            breakpoint_version=BREAKPOINT_TABLE_VERSION,
        ))
    return readings


def latest_reading(readings: list[Reading]) -> Optional[Reading]:
    """The newest reading by timestamp, or None. None, never a zeroed reading."""
    if not readings:
        return None
    return max(readings, key=lambda r: r.timestamp_utc)


def fetch_reading(school_id: str, lat: float, lon: float, *,
                  opener: Optional[Callable[[str], str]] = None,
                  source: str = SOURCE_OPEN_METEO) -> list[Reading]:
    """Fetch a day of readings. `opener` is injected so tests never hit the wire.

    The default opener is urllib; pass a stub returning a JSON string in tests.
    """
    import urllib.request
    opener = opener or (lambda url: urllib.request.urlopen(url, timeout=25).read().decode())
    url = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=pm2_5,pm10&timezone=Asia%2FKolkata&forecast_days=1"
    )
    payload = json.loads(opener(url))
    return parse_open_meteo(payload, school_id, source=source)
