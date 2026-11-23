"""Hitbox reach, threat zones, and spacing margins for Samurai Shodown II.

R3 (review P1-1, 2026-11-18): the reach table is a set of OBSERVED-reach
LOWER BOUNDS — the furthest hit each character's AI was actually sampled
landing in probes — NOT proven physical maxima. A rare long move that
never fired in sampling is unknown, not absent, so distances beyond a
table value decay linearly over an uncertainty band instead of dropping
to a "safe" 0. Per-character sampling provenance lives in
REACH_PROVENANCE (probe script, event count, confidence tier).

Provides physical attack reach boundaries for all 14 characters,
replacing heuristic distance guessing with grounded hitbox margins.

Author: Antigravity (TDD implemented for R2); R3 lower-bound semantics
+ provenance + uncertainty band by the mainline (review-adopted).
"""
from __future__ import annotations

from typing import Any
import numpy as np


# Throw opportunity threshold in pixels (close-range unblockable grab)
THROW_RANGE_THRESHOLD: float = 42.0

# R3 uncertainty band (review P1-1): beyond the observed lower bound the
# in_threat flag decays linearly to 0 over this band instead of snapping
# to 0. Wider than the table value = "unknown territory", narrower = low
# risk under current evidence (never proven safety).
UNCERTAINTY_BAND_FRAC: float = 0.15
UNCERTAINTY_BAND_MIN: float = 24.0

# 14 core characters reach specification (in pixels)
# Keys: light (A), medium (B), heavy (AB), crouch_heavy (2AB), max_threat
# (furthest OBSERVED hit = lower bound; see REACH_PROVENANCE).
# Ground-truth verified with mame_reach_rigorous.py (damage onset sampling):
#   - kyoshiro:薙刀 reach up to 225-244px (max_threat calibrated to 225)
#   - earthquake: close 76px, medium 131px, chain reach 215px (max_threat 233)
#   - nakoruru: close 37px direct; rush/mamahehe 111-128 is knowledge/onset
#     claim (max_threat 128, LOW confidence — direct lb is only 36)
#   - galford: light 71px, heavy 107px direct (max_threat 132 rush claim)
CHARACTER_REACH_TABLE: dict[str, dict[str, int]] = {
    "haowmaru":   {"light": 75, "medium": 95,  "heavy": 125, "crouch_heavy": 105, "max_threat": 128},
    "genjuro":    {"light": 75, "medium": 95,  "heavy": 125, "crouch_heavy": 100, "max_threat": 128},
    "nakoruru":   {"light": 37, "medium": 65,  "heavy": 85,  "crouch_heavy": 70,  "max_threat": 128},
    "galford":    {"light": 71, "medium": 85,  "heavy": 107, "crouch_heavy": 100, "max_threat": 132},
    "hanzo":      {"light": 70, "medium": 85,  "heavy": 115, "crouch_heavy": 100, "max_threat": 130},
    "kyoshiro":   {"light": 85, "medium": 125, "heavy": 165, "crouch_heavy": 165, "max_threat": 225},
    "wanfu":      {"light": 75, "medium": 105, "heavy": 155, "crouch_heavy": 120, "max_threat": 155},
    "genan":      {"light": 54, "medium": 80,  "heavy": 110, "crouch_heavy": 140, "max_threat": 140},
    "earthquake": {"light": 76, "medium": 131, "heavy": 185, "crouch_heavy": 215, "max_threat": 233},
    "chamcham":   {"light": 50, "medium": 70,  "heavy": 95,  "crouch_heavy": 105, "max_threat": 114},
    "sieger":     {"light": 70, "medium": 95,  "heavy": 130, "crouch_heavy": 115, "max_threat": 146},
    "nicotine":   {"light": 65, "medium": 85,  "heavy": 120, "crouch_heavy": 110, "max_threat": 132},
    "jubei":      {"light": 75, "medium": 95,  "heavy": 125, "crouch_heavy": 110, "max_threat": 125},
    "lad1":       {"light": 75, "medium": 95,  "heavy": 125, "crouch_heavy": 110, "max_threat": 125},
    "lad2":       {"light": 75, "medium": 95,  "heavy": 125, "crouch_heavy": 110, "max_threat": 125},
    "ukyo":       {"light": 75, "medium": 95,  "heavy": 125, "crouch_heavy": 110, "max_threat": 125},
    "charlotte":  {"light": 75, "medium": 95,  "heavy": 135, "crouch_heavy": 120, "max_threat": 135},
    "mizuki":     {"light": 80, "medium": 110, "heavy": 150, "crouch_heavy": 140, "max_threat": 150},
}


# R3 (review P1-1): sampling provenance per character. measured_lb = the
# furthest hit DIRECTLY observed landing in a probe (0 = never probed);
# confidence tiers: high = table value == directly measured (converged
# onset probe or n=10 rest10 match), medium = measured close to the
# (slightly higher) knowledge estimate, low = knowledge estimate far
# above the direct measurement (or no probe at all).
# Probes: probe_reach.txt (idle-P1, close-biased), probe_reach_rest10.txt
# (n=10 per char, 2026-11-18), mame_reach_rigorous.py + Antigravity onset
# probe (quake/kyoshiro convergence, 2026-11-17).
REACH_PROVENANCE: dict[str, dict[str, Any]] = {
    "haowmaru":   {"measured_lb": 128, "n_events": 10,
                   "probe": "probe_reach_rest10.txt",
                   "confidence": "high",
                   "note": "consistent 128 across all 10 events"},
    "genjuro":    {"measured_lb": 97, "n_events": 10,
                   "probe": "probe_reach_rest10.txt",
                   "confidence": "medium",
                   "note": "table 128 = long-slash knowledge estimate"},
    "nakoruru":   {"measured_lb": 36, "n_events": 10,
                   "probe": "probe_reach.txt (idle-P1)",
                   "confidence": "low",
                   "note": "direct close-only 36; max_threat 128 = "
                           "rush/mamahehe onset claim, never directly hit "
                           "at that range in our probes"},
    "galford":    {"measured_lb": 107, "n_events": 10,
                   "probe": "probe_reach.txt (idle-P1)",
                   "confidence": "medium",
                   "note": "direct 107; max_threat 132 = rush claim"},
    "hanzo":      {"measured_lb": 116, "n_events": 10,
                   "probe": "probe_reach_rest10.txt",
                   "confidence": "medium",
                   "note": "table 130 slightly above direct 116"},
    "kyoshiro":   {"measured_lb": 225, "n_events": 10,
                   "probe": "mame_reach_rigorous.py + onset probe",
                   "confidence": "high",
                   "note": "converged 225-244 naginata family"},
    "wanfu":      {"measured_lb": 80, "n_events": 10,
                   "probe": "probe_reach_rest10.txt",
                   "confidence": "low",
                   "note": "table 155 = knowledge estimate; direct only 80"},
    "genan":      {"measured_lb": 54, "n_events": 10,
                   "probe": "probe_reach_rest10.txt",
                   "confidence": "low",
                   "note": "table 140 = knowledge estimate; direct only 54 "
                           "(light poke); long moves never sampled"},
    "earthquake": {"measured_lb": 233, "n_events": 10,
                   "probe": "mame_reach_rigorous.py + onset probe "
                            "(chain family 185-233)",
                   "confidence": "high",
                   "note": "three-way convergence 2026-11-17"},
    "chamcham":   {"measured_lb": 114, "n_events": 10,
                   "probe": "probe_reach_rest10.txt",
                   "confidence": "high",
                   "note": "consistent 114 across all 10 events"},
    "sieger":     {"measured_lb": 146, "n_events": 10,
                   "probe": "probe_reach_rest10.txt",
                   "confidence": "high",
                   "note": "median 140, max 146"},
    "nicotine":   {"measured_lb": 132, "n_events": 10,
                   "probe": "probe_reach_rest10.txt",
                   "confidence": "high",
                   "note": "max 132 matches table"},
    "jubei":      {"measured_lb": 0, "n_events": 0,
                   "probe": "none",
                   "confidence": "low",
                   "note": "never probed; row mirrors lad1 estimate"},
    "lad1":       {"measured_lb": 92, "n_events": 10,
                   "probe": "probe_reach_rest10.txt",
                   "confidence": "medium",
                   "note": "direct 92; table 125 = generic estimate"},
    "lad2":       {"measured_lb": 0, "n_events": 0,
                   "probe": "none",
                   "confidence": "low",
                   "note": "never probed; row mirrors lad1 estimate"},
    "mizuki":     {"measured_lb": 114, "n_events": 10,
                   "probe": "probe_reach_rest10.txt",
                   "confidence": "low",
                   "note": "table 150 = knowledge estimate; direct 114"},
}

# Hardware-verified Neo-Geo WRAM character ID (UID + E_CHAR) mapping (probed from live MAME 2026-11-23)
# Note: 0x0A is reserved/Kuroko slot, so Charlotte..Mizuki occupy 0x0B..0x10.
SS2_CHAR_ID_MAP = {
    0x00: "haowmaru",
    0x01: "nakoruru",
    0x02: "hanzo",
    0x03: "galford",
    0x04: "wanfu",
    0x05: "ukyo",       # Ukyo Tachibana (legacy alias: lad1)
    0x06: "kyoshiro",
    0x07: "genan",
    0x08: "earthquake",
    0x09: "jubei",
    0x0B: "charlotte",
    0x0C: "genjuro",
    0x0D: "chamcham",
    0x0E: "sieger",
    0x0F: "nicotine",
    0x10: "mizuki",
}


def normalize_char_name(name: str | int | None) -> str:
    """Map character ID, state name, or string to canonical key."""
    if name is None:
        return "haowmaru"
    if isinstance(name, int):
        return SS2_CHAR_ID_MAP.get(name, "haowmaru")
    s = str(name).lower().strip()
    if s.isdigit():
        return SS2_CHAR_ID_MAP.get(int(s), "haowmaru")
    if s.endswith(".sta"):
        s = s[:-4]
    if s in CHARACTER_REACH_TABLE:
        return s
    for prefix in [
        "sieger", "mizuki", "jubei", "haowmaru", "earthquake", "genjuro",
        "galford", "nakoruru", "kyoshiro", "genan", "nicotine", "hanzo",
        "wanfu", "charlotte", "ukyo", "chamcham"
    ]:
        if s.startswith(prefix):
            return prefix
    # Map common aliases
    alias = {
        "haohmaru": "haowmaru",
        "lad1": "ukyo",
        "lad2": "ukyo",
        "ukyo": "ukyo",
        "kyo": "kyoshiro",
        "quake": "earthquake",
        "ugo": "sieger",
        "nico": "nicotine",
        "cham": "chamcham",
        "charlotte": "charlotte",
    }
    return alias.get(s, "haowmaru")


def get_char_reach(char: str | int | None, move_type: str = "heavy") -> int:
    """Retrieve reach in pixels for a character and attack category."""
    key = normalize_char_name(char)
    table = CHARACTER_REACH_TABLE.get(key, CHARACTER_REACH_TABLE["haowmaru"])
    return table.get(move_type, table.get("heavy", 125))


def get_max_threat_reach(char: str | int | None) -> int:
    """Retrieve the OBSERVED maximum threat range (lower bound) for the
    opponent — not a proven physical maximum (R3 semantics)."""
    key = normalize_char_name(char)
    table = CHARACTER_REACH_TABLE.get(key, CHARACTER_REACH_TABLE["haowmaru"])
    return table.get("max_threat", 125)


def uncertainty_band(threat: float) -> float:
    """Width of the unknown-territory band beyond the observed lower
    bound: max(24px, 15% of the threat value)."""
    return max(UNCERTAINTY_BAND_MIN, UNCERTAINTY_BAND_FRAC * float(threat))


def compute_hitbox_features(dx: float,
                            p1_char: str | int | None = "haowmaru",
                            p2_char: str | int | None = "haowmaru",
                            p1_in_air: bool = False,
                            p2_in_air: bool = False) -> np.ndarray:
    """Compute 5-dimensional normalized Hitbox awareness feature vector.

    Layout (5 dims):
      [0] p1_heavy_reach / 256.0      (P1 weapon reach scale, [0, 1])
      [1] p2_threat_reach / 256.0     (P2 OBSERVED threat lower bound /256)
      [2] tip_margin / 128.0          (Distance margin to P1 heavy slash
                                      tip, [-1, 1]) <= 0: in hit range;
                                      0 to 0.12: sweet spot; > 0.12: out
      [3] in_threat_flag  1.0 within the observed bound; LINEAR DECAY to
                          0 across the uncertainty band beyond it (an
                          unobserved longer move is unknown, not safe —
                          R3 review P1-1); 0 past the band = low risk
                          under current evidence
      [4] throwable_flag  (1.0 if abs(dx) <= 42px and neither airborne)
    """
    dist = float(abs(dx))
    p1_heavy = float(get_char_reach(p1_char, "heavy"))
    p2_threat = float(get_max_threat_reach(p2_char))

    # Margin: distance beyond P1's weapon tip
    # margin <= 0 -> inside weapon strike zone
    # margin > 0  -> beyond weapon reach (whiff risk)
    tip_margin = dist - p1_heavy
    tip_margin_norm = float(np.clip(tip_margin / 128.0, -1.0, 1.0))

    if dist <= p2_threat:
        in_threat = 1.0
    else:
        in_threat = max(0.0, 1.0 - (dist - p2_threat)
                        / uncertainty_band(p2_threat))
    throwable = 1.0 if (dist <= THROW_RANGE_THRESHOLD and not p1_in_air and not p2_in_air) else 0.0

    vec = np.zeros(5, dtype=np.float32)
    vec[0] = float(np.clip(p1_heavy / 256.0, 0.0, 1.0))
    vec[1] = float(np.clip(p2_threat / 256.0, 0.0, 1.0))
    vec[2] = tip_margin_norm
    vec[3] = in_threat
    vec[4] = throwable

    return vec
