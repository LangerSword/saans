"""SAANS tier rules engine — pure, deterministic, no network.

THE INVARIANT: this module is the only thing that sets a tier.
The advisory agent can only write advisory text; it never sets a tier.

AQI bands use the US AQI scale (Open-Meteo `us_aqi`), which is what the
verified feed returns. School actions are SAANS's own draft (CPCB band
thresholds), not copied from an official school-closure policy.
"""

from dataclasses import dataclass
from typing import Optional

# US AQI band edges (lower bound inclusive). Tiers 0..4.
# (max_us_aqi_exclusive, band_name)
BANDS = [
    (101, "good"),          # 0-100
    (201, "moderate"),      # 101-200
    (301, "poor"),          # 201-300
    (401, "very_poor"),     # 301-400
    (float("inf"), "severe"),  # 401+
]

TIER_OF_BAND = {name: i for i, (_max, name) in enumerate(BANDS)}


def aqi_to_band(us_aqi: float) -> str:
    """Map a US AQI value to a band name. Pure function, testable offline."""
    if us_aqi < 0:
        raise ValueError(f"us_aqi must be >= 0, got {us_aqi}")
    for max_edge, name in BANDS:
        if us_aqi < max_edge:
            return name
    return "severe"  # unreachable, keeps type checkers happy


def aqi_to_tier(us_aqi: float) -> int:
    """US AQI value -> tier index 0..4."""
    return TIER_OF_BAND[aqi_to_band(us_aqi)]


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
