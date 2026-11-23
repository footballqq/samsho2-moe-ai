"""C2 reflex engine (design v3 §二): tactical intents -> base actions under
range gates, plus high-priority override reflexes.

Pure logic — no bridge access. The env (intent_mode) feeds dx (world px,
p2x - p1x) and the P2 flag tuple from entity_features and receives a base
action id for its existing Discrete(12) machinery. Range gates are v1
estimates — tune from C3 episode data, never by hand-waving.

Deep-dive lesson baked in: direction is ALWAYS derived from the dx sign;
no direction literals.

R3 (review P1-2, plan §二B) — reflex priority table (locked by test_m29):
  1. anti_air            override_reflex
  2. punish (confirmed counter-hit window)   override_reflex
  3. approach-downed     override_reflex
  4. translated policy intent
  The R3 threat probe is NOT in this chain: the 6 observable flags cannot
  distinguish attack startup / active / recovery frames (the punishable
  family covers attack AND counterable recovery), so the probe is
  LOG-ONLY — the env counts hits in info["threat_observed"] and never
  overrides a move. The R3 whiff guard (suppress_far_air) sits BEFORE the
  env's jump-slash dispatch and only touches AIRBORNE attacks; ground
  attacks keep translate()'s existing range gates.
"""
from __future__ import annotations

from mame_hitbox import get_char_reach  # noqa: E402  (pure table, no cycle)
from mame_types import (MSK_DOWN, MSK_LEFT, MSK_RIGHT, MSK_UP)  # noqa: E402

# tactical intents (design v3 §C1; C3's Discrete(8) input space; R2 adds
# the 9th `jump` — intent models sized by env n_intents, legacy 8 kept)
INTENTS = ["approach", "retreat", "poke", "slash", "anti_air", "punish",
           "fireball", "guard", "jump"]

# base action ids (mame_gym Discrete(12))
ACTIONS = {"idle": 0, "walkL": 1, "walkR": 2, "jump": 3, "jab": 4,
           "heavy": 5, "kick": 6, "crouch": 7, "uppercut": 8, "rush": 9,
           "fireball": 10, "sake": 11}

# range gates (world px, v1 estimates — tune from C3 data)
POKE_RANGE = 90        # jab connects
SLASH_RANGE = 120      # heavy connects
PUNISH_RANGE = 130     # heavy during the opponent's recovery
AA_RANGE = 130         # uppercut anti-air reach
FIREBALL_MIN = 200     # far enough that the fireball is safe

# audit 3.2: per-character reach calibration — a longer-reach opponent
# pushes OUR safety margin out (their pokes hit where ours don't); a
# short-reach opponent pulls it in. Keyed by charID (uid+0xF6), values in
# world px added to every range gate. v1 estimates from matchup play —
# replace with episode-measured reach when C3 data exists.
OPP_RANGE_OFFSET = {
    0x05: 25,    # Ukyo — longest poke in the roster
    0x06: 30,    # Kyoshiro — naginata reach
    0x08: 50,    # Earthquake — massive chain reach (215px ground sweep, 233px max threat)
    0x0C: 15,    # Genjuro — long heavy slash
    0x0D: -15,   # Cham Cham — short reach
    0x01: -15,   # Nakoruru — short reach
}


def _gates(char_id: int) -> tuple[int, int, int, int, int]:
    """Range gates calibrated for the current opponent."""
    off = OPP_RANGE_OFFSET.get(char_id, 0)
    return (POKE_RANGE + off, SLASH_RANGE + off, PUNISH_RANGE + off,
            AA_RANGE + off, max(FIREBALL_MIN + off // 2, 150))


def _toward(dx: int) -> int:
    return ACTIONS["walkR"] if dx > 0 else ACTIONS["walkL"]


def _away(dx: int) -> int:
    return ACTIONS["walkL"] if dx > 0 else ACTIONS["walkR"]


def translate(intent: str, dx: int, p2_flags: tuple,
              char_id: int = 0) -> int:
    """Intent -> base action under range gates (calibrated per opponent);
    out-of-range attack intents fall back to approaching (closing the
    distance IS the intent's setup)."""
    poke, slash, punish_r, aa_r, fb_min = _gates(char_id)
    air, hit, block, punish, down, up = p2_flags
    dist = abs(dx)
    if intent == "approach":
        return _toward(dx)
    if intent == "retreat":
        return _away(dx)
    if intent == "poke":
        return ACTIONS["jab"] if dist <= poke else _toward(dx)
    if intent == "slash":
        if char_id == 0x08:
            # Earthquake matchup (user review): weapon physically caps at 120px;
            # 120-215px is Earthquake's lethal ground chain sweep zone.
            # Do NOT whiff at 120-170px and do NOT slow-walk into his low sweep.
            if dist <= SLASH_RANGE:
                return ACTIONS["heavy"]
            if dist <= 215:
                return ACTIONS["jump"]
            return _toward(dx)
        return ACTIONS["heavy"] if dist <= slash else _toward(dx)
    if intent == "anti_air":
        return (ACTIONS["uppercut"] if air and dist <= aa_r
                else _toward(dx))
    if intent == "punish":
        return (ACTIONS["heavy"] if punish and dist <= punish_r
                else _toward(dx))
    if intent == "fireball":
        return (ACTIONS["fireball"] if dist >= fb_min else _toward(dx))
    if intent == "guard":
        return _away(dx)
    if intent == "jump":
        # R2 P0-3: the direction is decided at env dispatch (jump_mask_for
        # from dx/distance) — the intent only claims the jump
        return ACTIONS["jump"]
    raise ValueError(f"unknown intent {intent!r}")


def jump_mask_for(dx: int, char_id: int = 0) -> int:
    """R2 directional jump mask (UP + optional direction): far -> jump-in,
    inside poke range -> jump away, else neutral UP. Direction is ALWAYS
    derived from the dx sign (deep-dive lesson)."""
    poke = _gates(char_id)[0]
    d = abs(dx)
    toward = MSK_RIGHT if dx > 0 else MSK_LEFT
    away = MSK_LEFT if dx > 0 else MSK_RIGHT
    if d > 150:
        return MSK_UP | toward
    if d <= poke:
        return MSK_UP | away
    return MSK_UP


def override_reflex(dx: int, p2_flags: tuple, char_id: int = 0) -> int | None:
    """High-priority reflexes; a non-None return overwrites the translated
    action. Order: anti-air > punish window > press the downed opponent."""
    _, _, punish_r, aa_r, _ = _gates(char_id)
    air, hit, block, punish, down, up = p2_flags
    dist = abs(dx)
    if air and dist <= aa_r:
        return ACTIONS["uppercut"]
    if punish:
        # Opponent in hitstun/dizzy/recovery: strike if in range, rush forward if distant
        return ACTIONS["heavy"] if dist <= punish_r else _toward(dx)
    if down:
        return _toward(dx)
    return None


def anti_spam(act: int, streak: int, dx: int,
              p2_flags: tuple) -> int | None:
    """Reflex-side anti-repetition (user spectate 2026-11-15: the C3
    policy degraded to light-slash spam within each round — the retired
    reward penalties removed the only anti-repetition force, and the
    deterministic translation parked on one move). When an ATTACK has
    repeated into streak >= 3 while the opponent is in neutral (not
    hit/block/air — i.e. the pokes are NOT connecting), walk away one step
    to reset the spacing instead of feeding the opponent's range advantage
    (Ukyo's crouching medium outranges Haohmaru's light slash)."""
    if streak < 3:
        return None
    air, hit, block, punish, down, up = p2_flags
    if air or hit or block or down or up:
        return None                      # opponent states own the rhythm
    if act in (ACTIONS["jab"], ACTIONS["heavy"], ACTIONS["kick"],
               ACTIONS["crouch"], ACTIONS["fireball"], ACTIONS["sake"]):
        return _away(dx)
    return None


def reflex_action(intent_id: int, dx: int, p2_flags: tuple,
                  char_id: int = 0) -> int:
    """Full C2 pipeline for the env: override reflex first, then translate."""
    act = override_reflex(dx, p2_flags, char_id)
    if act is not None:
        return act
    return translate(INTENTS[intent_id], dx, p2_flags, char_id)


# ------------------------------------------------- R3 guards (plan §二B)
# Whiff guard (air path only): an airborne attack dispatched farther than
# the heavy-slash tip + a 0.15 normalized margin would whiff the air
# slash; suppress it (the env drifts instead). Derivation: reach(haowmaru,
# heavy) + int(0.15 * 128) = 125 + 19 = 144px. Ground attacks keep
# translate()'s range gates — no double gating.
TIP_MARGIN_GUARD_NORM = 0.15
AIR_SLASH_MAX_DIST = (get_char_reach("haowmaru", "heavy")
                      + int(TIP_MARGIN_GUARD_NORM * 128.0))

_AIR_GUARD_ACTS = frozenset(ACTIONS[k] for k in
                            ("jab", "heavy", "kick", "crouch", "uppercut",
                             "rush", "fireball", "sake"))


def suppress_far_air(act: int, dist: int, p1_air: bool) -> int | None:
    """R3 whiff guard (air path only): airborne ATTACK beyond
    AIR_SLASH_MAX_DIST would whiff -> replacement A_IDLE (drift); any
    other case returns None (unchanged). Pure — the env calls it right
    before its jump-slash dispatch."""
    if p1_air and dist > AIR_SLASH_MAX_DIST and act in _AIR_GUARD_ACTS:
        return ACTIONS["idle"]
    return None


def threat_guard_probe(dist: int, p2_flags: tuple,
                       threat_reach: float) -> bool:
    """R3 threat OBSERVATION (LOG-ONLY, plan §二B2 / review P1-2): True
    when we stand inside the opponent's observed-reach bound while their
    state is in the punishable family — the only attack-correlated bit
    the 6 flags offer, and it also covers counterable recovery, which is
    exactly why this probe must never override an action (it would step
    out of punish windows). The env counts hits in info["threat_observed"]
    for false-positive/negative calibration; no action is produced."""
    if p2_flags[3] <= 0.5:            # punish family flag
        return False
    return dist <= threat_reach
