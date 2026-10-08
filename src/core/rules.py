"""SAANS tier rules engine — pure, deterministic, no network.

THE INVARIANT: this module is the only thing that sets a tier.
The advisory agent can only write advisory text; it never sets a tier.

AQI bands are the CPCB National AQI bands (2014), because the audience is Indian
schools and the tiers map to CPCB categories.

IMPORTANT: this module takes POLLUTANT CONCENTRATIONS (ug/m3), not a precomputed
AQI. Open-Meteo's CAMS feed returns concentrations plus `us_aqi`, and US AQI is
NOT CPCB AQI. Measured on a live Delhi day, feeding `us_aqi` straight in put
38% of hours in the wrong tier (evidence: docs/screens/scale-check.txt). So we
compute CPCB AQI ourselves from pm2_5 and pm10 using CPCB's breakpoints.

CPCB sources:
- Breakpoints: app.cpcbccr.com/ccr_docs/AQI-Calculator.xls ("Breakpoints" sheet)
- Method:    app.cpcbccr.com/ccr_docs/How_AQI_Calculated.pdf (sub-index formula)
"""

from dataclasses import dataclass
from typing import Optional, Tuple

# CPCB National AQI (2014) breakpoints, 24-hour, ug/m3.
# (conc_low, conc_high, index_low, index_high). CPCB's bands are INTEGER-spaced
# with a gap between them (band 1 ends at 30, band 2 starts at 31). CPCB states
# Cp is the "truncated concentration", so sub_index() floors to an integer first;
# with integer concentrations these bands are contiguous with no gaps.
# Source: CPCB AQI Calculator, "Breakpoints" sheet.
# CPCB National AQI (2014) breakpoints, 24-hour, ug/m3.
# (conc_low, conc_high, index_low, index_high).
#
# SOURCE OF TRUTH: CPCB "National Air Quality Index" final report, Tables 3.5
# (PM10) and 3.6 (PM2.5), fetched 2026-10-09 from
# www.cpcb.nic.in/displaypdf.php. Those tables give the UPPER BOUND of each
# AQI category:
#   PM2.5: Good 30, Satisfactory 60, Moderate 90, Poor 120, Very Poor 250
#   PM10:  Good 50, Satisfactory 100, Moderate 250, Poor 350, Very Poor 430
# Category boundaries are shared between adjacent bands (30 is the top of Good
# and the bottom of Satisfactory), so a value exactly on a boundary resolves
# cleanly. CPCB also states Cp is the "truncated concentration", so sub_index()
# floors to an integer before the lookup.
#
# Verified against CPCB's own worked example (How_AQI_Calculated.pdf):
#   PM2.5 = 31 -> 51, 45 -> 75, 60 -> 100.
# CPCB National AQI (2014) breakpoints, 24-hour, ug/m3.
# (conc_low, conc_high, index_low, index_high).
#
# SOURCE OF TRUTH: CPCB "National Air Quality Index" report, Tables 3.5 (PM10)
# and 3.6 (PM2.5), fetched 2026-10-09 from www.cpcb.nic.in. Each table lists the
# concentration range of every category as INTEGER ranges:
#   PM2.5: Good 0-30, Satisfactory 31-60, Moderate 61-90, Poor 91-120,
#          Very Poor 121-250, Severe 251+ (top of scale 500)
#   PM10:  Good 0-50, Satisfactory 51-100, Moderate 101-250, Poor 251-350,
#          Very Poor 351-430, Severe 431+ (top of scale 500)
#
# The interpolation bounds below are each band's OWN integer range. This is not
# cosmetic: a band written as (30,60)->(51,100) gives 52.6 at 31 ug/m3, but
# (31,60)->(51,100) gives 51, which is what CPCB's worked example states
# (How_AQI_Calculated.pdf: "the PM2.5 sub-index is 51 at a concentration of
# 31 ug/m3, 75 at 45 ug/m3, and 100 at 60 ug/m3"). Both are asserted in
# tests/test_cpcb_aqi.py, so the structure cannot silently drift.
#
# CPCB also states Cp is the "truncated concentration", so sub_index() floors to
# an integer before the lookup; with integer concentrations these bands are
# contiguous with no gaps.
CPCB_BREAKPOINTS = {
    "pm2_5": [
        (0.0, 30.0, 0.0, 50.0),
        (31.0, 60.0, 51.0, 100.0),
        (61.0, 90.0, 101.0, 200.0),
        (91.0, 120.0, 201.0, 300.0),
        (121.0, 250.0, 301.0, 400.0),
        (251.0, 380.0, 401.0, 500.0),
    ],
    "pm10": [
        (0.0, 50.0, 0.0, 50.0),
        (51.0, 100.0, 51.0, 100.0),
        (101.0, 250.0, 101.0, 200.0),
        (251.0, 350.0, 201.0, 300.0),
        (351.0, 430.0, 301.0, 400.0),
        (431.0, 510.0, 401.0, 500.0),
    ],
}

# CPCB's real rule is "at least 3 pollutants, one of which must be PM2.5 or PM10".
# The feed gives us particulates reliably, so we compute a PM-only index and say
# so: a documented simplification, not the full CPCB index. In Delhi winter PM
# dominates the index, but it is still an approximation.
PM_ONLY_POLLUTANTS = ("pm2_5", "pm10")

# CPCB AQI band edges. Tiers 0..4. (max_aqi_exclusive, band_name)
BANDS = [
    (101, "good"),          # 0-100
    (201, "moderate"),      # 101-200
    (301, "poor"),          # 201-300
    (401, "very_poor"),     # 301-400
    (float("inf"), "severe"),  # 401+
]

TIER_OF_BAND = {name: i for i, (_max, name) in enumerate(BANDS)}


def aqi_to_band(aqi: float) -> str:
    """Map a CPCB AQI value to a band name. Pure function, testable offline."""
    if aqi < 0:
        raise ValueError(f"aqi must be >= 0, got {aqi}")
    for max_edge, name in BANDS:
        if aqi < max_edge:
            return name
    return "severe"  # unreachable, keeps type checkers happy


def aqi_to_tier(aqi: float) -> int:
    """CPCB AQI value -> tier index 0..4."""
    return TIER_OF_BAND[aqi_to_band(aqi)]


def sub_index(conc: float, pollutant: str) -> float:
    """CPCB sub-index for one pollutant, via CPCB's published formula:

        Ip = ((IHi - ILo) / (BPHi - BPLo)) * (Cp - BPLo) + ILo

    Raises ValueError on a negative concentration or a value above the top band.
    """
    if conc < 0:
        raise ValueError(f"{pollutant} concentration must be >= 0, got {conc}")
    # CPCB: "Cp = truncated concentration of pollutant p". Floor to an integer
    # so the integer-gapped bands resolve cleanly and we match CPCB's calculator.
    conc = float(int(conc))
    table = CPCB_BREAKPOINTS[pollutant]
    for bp_lo, bp_hi, i_lo, i_hi in table:
        if bp_lo <= conc <= bp_hi:
            return (i_hi - i_lo) / (bp_hi - bp_lo) * (conc - bp_lo) + i_lo
    raise ValueError(
        f"{pollutant}={conc} is above the highest CPCB breakpoint {table[-1][1]}"
    )


def aqi_from_pm(pm2_5: Optional[float], pm10: Optional[float]) -> Tuple[float, str]:
    """CPCB-style AQI from concentrations. Returns (aqi, dominant_pollutant).

    CPCB's rule: overall AQI is the MAXIMUM sub-index across pollutants. We have
    particulates, so this is a PM-only index (see PM_ONLY_POLLUTANTS).

    At least one of PM2.5/PM10 must be present, because CPCB requires one of them
    to compute an index at all.
    """
    subs = []
    if pm2_5 is not None:
        subs.append((sub_index(pm2_5, "pm2_5"), "pm2_5"))
    if pm10 is not None:
        subs.append((sub_index(pm10, "pm10"), "pm10"))
    if not subs:
        raise ValueError("need at least one of pm2_5 / pm10 to compute an AQI")
    aqi, pollutant = max(subs, key=lambda t: t[0])
    return round(aqi, 1), pollutant


# School actions per band. SAANS's own draft — verify before the blog.
ACTIONS = {
    "good": "Normal day.",
    "moderate": "Sensitive students (asthma) limit outdoor exertion.",
    "poor": "PE and recess indoors. No outdoor assembly. Mask advisory.",
    "very_poor": "Indoor only. Shorten the day or go hybrid. Notify parents.",
    "severe": "Recommend closure or online classes. Escalate to authorities.",
}


@dataclass(frozen=True)
class TierState:
    """What we persist about a school's current air status."""
    tier: int
    band: str
    aqi: float
    prev_tier: Optional[int] = None   # last alerted tier, for hysteresis
    pending_tier: Optional[int] = None  # candidate tier during downgrade confirmation
    pending_count: int = 0              # consecutive readings at pending_tier


def initial_state(aqi: float) -> TierState:
    """First-ever reading for a school: adopt immediately, no hysteresis needed."""
    band = aqi_to_band(aqi)
    return TierState(tier=TIER_OF_BAND[band], band=band, aqi=aqi)


def _hysteresis_tier(state: TierState, new_tier: int) -> int:
    """Confirm a DOWNGRADE across two readings before adopting it.

    Upgrades adopt immediately (safety). Downgrades need 2 consecutive
    readings so the tier doesn't flap at a band boundary and the principal
    doesn't get repeat alerts.
    """
    if new_tier >= state.tier:
        return new_tier  # upgrade or same -> immediate
    # downgrade candidate
    if state.pending_tier == new_tier:
        return new_tier if state.pending_count >= 1 else state.tier
    return state.tier  # first sight of a lower tier: hold current, remember candidate


def next_state(state: TierState, new_aqi: float) -> TierState:
    """Given the persisted state and a fresh reading, compute the next state.

    - Upgrade (tier rises): adopt immediately.
    - Same tier: adopt, refresh aqi.
    - Downgrade: only adopt after 2 consecutive readings at the lower tier.
    """
    new_band = aqi_to_band(new_aqi)
    new_tier = TIER_OF_BAND[new_band]

    if new_tier > state.tier:
        # upgrade -> immediate, clear any pending downgrade
        return TierState(tier=new_tier, band=new_band, aqi=new_aqi,
                         prev_tier=state.tier)
    if new_tier == state.tier:
        return TierState(tier=new_tier, band=new_band, aqi=new_aqi,
                         prev_tier=state.prev_tier)

    # downgrade path
    if state.pending_tier == new_tier and state.pending_count >= 1:
        # second consecutive sighting -> adopt
        return TierState(tier=new_tier, band=new_band, aqi=new_aqi,
                         prev_tier=state.tier)
    # first sighting (or count reset) -> hold, record candidate
    return TierState(tier=state.tier, band=state.band, aqi=new_aqi,
                     prev_tier=state.prev_tier,
                     pending_tier=new_tier, pending_count=1)


def band_changed(old: TierState, new: TierState) -> bool:
    """True if the effective tier changed -> should trigger a new alert."""
    return old.tier != new.tier
