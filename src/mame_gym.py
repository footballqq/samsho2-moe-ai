"""Gymnasium round env for SS2 — full-moveset anti-cheese tier (2026-11-07).

Reward/observation channels unchanged from the pixel-bar tier (both HPs from
PIXEL BARS — ground truth; P2 memory addr is contaminated mid-round; timer
from memory). NEW per user goal "全招式合理地赢, 不许套路 spam":

  * Discrete(12): idle/walkL/walkR/jump/jab(A)/heavy(B)/kick(C)/crouch(↓A)/
    uppercut(dp+A)/rush(dp+C)/fireball(qcf+A)/sake(qcb+A)
  * repetition penalty: same action >=4 in a row costs -0.02*(streak-3),
    capped at 10 extra steps of streak (anti "下铲/火球 spam")
  * fast-win bonus: KO in <120 steps adds +0.5 (anti stalling)
  * KO termination: 2 consecutive zero-bar reads; timer 0 via memory channel

Requires the .venv python (gymnasium). The bridge stack is stdlib-only.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

import gymnasium as gym  # noqa: E402
import numpy as np  # noqa: E402
from gymnasium import spaces  # noqa: E402

from mame_client import BridgeSession  # noqa: E402
from mame_features_schema import frame_width, stacked_size  # noqa: E402
from mame_hitbox import get_max_threat_reach  # noqa: E402
from mame_reflex import (INTENTS, anti_spam, reflex_action,  # noqa: E402
                         suppress_far_air, threat_guard_probe)
from mame_hud import BarReader, count_bars  # noqa: E402
from mame_macro import Moveset  # noqa: E402
from mame_types import (DIR_MASKS, MSK_A, MSK_B, MSK_C, MSK_DOWN,  # noqa: E402
                        MSK_LEFT, MSK_RIGHT, MSK_UP)

A_TIMER, A_CAM = 0x100AC5, 0x1009FA

# action ids
(A_IDLE, A_WL, A_WR, A_JUMP, A_JAB, A_HEAVY, A_KICK, A_CROUCH,
 A_UPPERCUT, A_RUSH, A_FIREBALL, A_SAKE) = range(12)
# R2 (plan v4): air slash — 方案A stateful dispatch (ground -> UP tap,
# airborne -> MSK_A tap). Probe-verified 2026-11-17: air-attack state word
# family 0x0103, ~46f air window, ground Y=224 / apex ~100.
A_JUMPSLASH = 12
ATTACK_ACTIONS = {A_JAB, A_HEAVY, A_KICK, A_CROUCH, A_UPPERCUT, A_RUSH,
                  A_FIREBALL, A_SAKE, A_JUMPSLASH}
WHIFF_WINDOW_MELEE = 8        # steps (~1s) for a melee attack to connect
WHIFF_WINDOW_PROJ = 20        # fireball travels: longer window
# T20 scene-wait budget: KO-banner / TIME-OVER / refill scenes despawn the
# entity structs for a few hundred frames; ~80 probes x 6f ≈ 8 game-seconds
SCENE_WAIT_CALLS = 80

# T5 deliverable (2026-11-11): game-written damage latch — set on every
# hit, 0 in all whiffs, and it reads THROUGH the camera zoom that hides
# the pixel HUD (the zoom used to turn real hits into dealt=0 whiffs).
T5_DAMAGE_LATCH = 0x105ED3
# L2 observables (T5 verified 2026-11-11): see test_m11_l2obs.py
T5_ATTACK_STATE = 0x100110    # P1 move state (idle/jab/strong ...)
T5_HITSTUN_TIMER = 0x105EE9   # opponent hitstun countdown

# Verified character max HP (stamina) specifications in SS2.
# P1 is always Haohmaru (128.0). P2 stamina varies by character:
# Most characters are 128 (0x80); Ukyo (lad1) is 164; Sieger is 186.
CHAR_MAX_HP_TABLE: dict[str, float] = {
    "haowmaru": 128.0,
    "genjuro": 128.0,
    "nakoruru": 128.0,
    "galford": 128.0,
    "hanzo": 128.0,
    "kyoshiro": 128.0,
    "wanfu": 128.0,
    "genan": 128.0,
    "earthquake": 128.0,
    "chamcham": 128.0,
    "sieger": 186.0,
    "nicotine": 128.0,
    "jubei": 128.0,
    "ukyo": 164.0,
    "charlotte": 128.0,
    "lad1": 164.0,   # Legacy alias for Ukyo
    "lad2": 128.0,
    "mizuki": 128.0,
}



def whiff_connected(dealt: float, latch_now: int, latch_at_open: int) -> bool:
    """Whiff-window connection test: pixel damage OR latch increase.

    Latch DECREASES/resets are ignored (asymmetric safety: a missed
    penalty is benign, a fake hit reward is not)."""
    if dealt > 0:
        return True
    try:
        return latch_now > latch_at_open
    except TypeError:            # latch unreadable (-1 layout mismatch)
        return False


def _field(v: tuple[int, ...], addr: int, width: int = 1) -> int:
    off = addr - 0x100000
    idx, sh = off // 4, (off % 4) * 8
    if idx >= len(v):
        return -1
    mask = 0xFF if width == 1 else 0xFFFF
    return (v[idx] >> sh) & mask


# ------------------------------------------------- R3 reward shaping
# (review P2, plan §二C): one damage event = the T5 damage latch rising
# above its high-water mark. Per-decision-step coalescing (a multi-hit
# string landing inside one 6-frame step counts ONCE); a lower latch
# reading = reset (scene/KO/refill) and the mark tracks DOWN so the
# first new event still fires. Labels read the PREVIOUS step's P2 flags
# (state at contact). Overlap (punish + airborne) -> single HIGHER
# reward (counter-hit), never stacked.
REWARD_COUNTER_HIT = 0.3
REWARD_ANTI_AIR = 0.2


def hit_event_reward(latch_now: int, hwm: int,
                     p2_flags_prev: tuple) -> tuple[float, str, int]:
    """(reward, kind, new_hwm) for one decision step; kind "" = no event."""
    if latch_now < 0:
        return 0.0, "", hwm
    if latch_now < hwm:               # latch reset detected: track down
        return 0.0, "", latch_now
    if latch_now > hwm:
        if p2_flags_prev[3] > 0.5:    # punish family -> counter-hit
            return REWARD_COUNTER_HIT, "counter", latch_now
        if p2_flags_prev[0] > 0.5:    # airborne -> anti-air
            return REWARD_ANTI_AIR, "anti_air", latch_now
        return 0.0, "", latch_now     # plain hit: counted, unrewarded
    return 0.0, "", hwm


def l2_features(v: tuple[int, ...]) -> tuple[float, float, float]:
    """L2 observation features (T5-verified channels), normalized /255.
    A compact vals layout (addresses missing) yields zeros, not a crash."""
    def n(addr):
        off = addr - 0x100000
        if off // 4 >= len(v):
            return 0.0
        return ((v[off // 4] >> ((off % 4) * 8)) & 0xFF) / 255.0
    return (n(T5_ATTACK_STATE), n(T5_DAMAGE_LATCH), n(T5_HITSTUN_TIMER))


# ------------------------------------------------------ entity obs (T11/A1)
# Community fbneo-training-mode map, LIVE-verified 2026-11-14
# (src/test_t11_a0_precheck.py 11/11 + diag_t11_xconfirm.py):
#   uid ptrs @0x100A46/0x100A4A (u32, per-round entity bases), offsets below.
# CAUTION: the WRAM dump tuple is BIG-ENDIAN; legacy `_field` above is an
# LE extractor that actually reads addr+2 — kept ONLY for frozen legacy
# channels (timer/l2) whose semantics were trained on it. All new code
# must use `_field_be`.
P1UID_LOC, P2UID_LOC = 0x100A46, 0x100A4A
E_X, E_Y, E_DIRECTION, E_HEALTH, E_HEALTHADD = 0x4E, 0x50, 0x7F, 0xBB, 0xBC
E_STUN, E_METER, E_METERADD, E_STATE, E_CHAR = 0xC1, 0xF0, 0x114, 0xE6, 0xF6
A_TIMER_BE, A_CAM_BE = 0x100AC6, 0x1009F8


def _field_be(v: tuple[int, ...], addr: int, width: int = 1) -> int:
    """Big-endian extraction from the WRAM dump (byte stream semantics)."""
    off = addr - 0x100000
    i, k = off // 4, off % 4
    out = 0
    for j in range(width):
        wi = i + (k + j) // 4
        if wi >= len(v):
            return -1
        out = (out << 8) | ((v[wi] >> (8 * (3 - (k + j) % 4))) & 0xFF)
    return out


def decode_state_flags(state_raw: int) -> tuple[float, ...]:
    """6 orthogonal physical flags from the raw state word (community
    ranges; per-character drift is a B-phase check). Order: airborne,
    hitstun, blockstun, punishable (attack/special/recovery = counter-
    hit window), knocked_down, getting_up."""
    return (
        1.0 if state_raw in (0x0006, 0x0008, 0x0009) else 0.0,
        1.0 if (0x0304 <= state_raw <= 0x0308 or state_raw == 0x0015
                or 0x0500 <= state_raw <= 0x051F) else 0.0,
        1.0 if 0x030D <= state_raw <= 0x0313 else 0.0,
        1.0 if (0x0100 <= state_raw <= 0x0200
                or 0x001F <= state_raw <= 0x0033
                or 0x0400 <= state_raw <= 0x0402) else 0.0,
        1.0 if state_raw == 0x0338 else 0.0,
        1.0 if state_raw == 0x0315 else 0.0,
    )


def resolve_entity_uids(sess, max_settle: int = 8) -> tuple[int, int]:
    """UID safety gate (deep-dive §细节 1): after machine:load there is a
    1-3 frame settle gap where the pointers may read 0/stale — validate the
    WRAM range and retry one frame at a time before dereferencing."""
    p1 = p2 = 0
    for _ in range(max_settle):
        p1 = sess.call("read_mem", P1UID_LOC, 4)
        p2 = sess.call("read_mem", P2UID_LOC, 4)
        if (0x102000 <= p1 <= 0x10F000 and 0x102000 <= p2 <= 0x10F000
                and p1 != p2):
            return p1, p2
        sess.call("action", step_frames=1)
    raise RuntimeError(
        f"entity uid resolution failed: p1={p1:#x} p2={p2:#x}")


from mame_hitbox import compute_hitbox_features


def entity_features(v: tuple[int, ...], p1uid: int, p2uid: int,
                    p1b: float, p2b: float,
                    y_obs: bool = False,
                    hitbox_obs: bool = False,
                    p2_char_name: str | None = None) -> tuple[float, ...]:
    """25-dim entity observation (design v3 §C1 + deep-dive §细节 3/4):
    dx_signed, dist_abs, bars(2), meters(2), stuns(2), P2 flags(6),
    P1 flags(6), directions(2), p2 char, timer, camera. R2 y_obs=True
    appends y1/y2 (uid+0x50, /256) -> 27 dims = 54 stacked.
    R2 hitbox_obs=True appends 5 Hitbox channels -> 32 dims = 64 stacked."""
    x1 = _field_be(v, p1uid + E_X, 2)
    x2 = _field_be(v, p2uid + E_X, 2)
    dx = (x2 - x1) if (x1 >= 0 and x2 >= 0) else 0
    dx_n = max(-512.0, min(512.0, dx)) / 512.0
    dist = min(abs(dx), 512) / 512.0
    m1 = min(_field_be(v, p1uid + E_METER, 1)
             + _field_be(v, p1uid + E_METERADD, 1), 0x20) / 0x20
    m2 = min(_field_be(v, p2uid + E_METER, 1)
             + _field_be(v, p2uid + E_METERADD, 1), 0x20) / 0x20
    s1 = _field_be(v, p1uid + E_STUN, 1) / 255.0
    s2 = _field_be(v, p2uid + E_STUN, 1) / 255.0
    f2 = decode_state_flags(_field_be(v, p2uid + E_STATE, 2))
    f1 = decode_state_flags(_field_be(v, p1uid + E_STATE, 2))
    d1 = float(_field_be(v, p1uid + E_DIRECTION, 1))
    d2 = float(_field_be(v, p2uid + E_DIRECTION, 1))
    ch2 = _field_be(v, p2uid + E_CHAR, 1) / 15.0
    t = _field_be(v, A_TIMER_BE, 1)
    tf = max(0.0, min(1.0, (0x99 - t) / 0x99))
    cam = _field_be(v, A_CAM_BE, 2) / 65535.0
    # R2: vertical position (probe 2026-11-17: ground 224, apex ~100,
    # UP = smaller y; /256 keeps ground at 0.875)
    base = ((dx_n, dist, p1b, p2b, m1, m2, s1, s2)
            + f2 + f1 + (d1, d2, ch2, tf, cam))
    if y_obs:
        y1 = _field_be(v, p1uid + E_Y, 2) / 256.0
        y2 = _field_be(v, p2uid + E_Y, 2) / 256.0
        base = base + (y1, y2)
    if not hitbox_obs:
        return base
    # R2: 5-dim Hitbox physical awareness features
    p1_air = bool(f1[0] > 0.5)
    p2_air = bool(f2[0] > 0.5)
    p2_c = p2_char_name if p2_char_name else int(_field_be(v, p2uid + E_CHAR, 1))
    hb = compute_hitbox_features(
        dx=dx,
        p1_char="haowmaru",
        p2_char=p2_c,
        p1_in_air=p1_air,
        p2_in_air=p2_air
    )
    return base + tuple(float(x) for x in hb)


class SS2RoundEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, sess: BridgeSession | None = None,
                 instance: str = "rl",
                 speed: int = 4, step_frames: int = 6, max_steps: int = 800,
                 repeat_penalty: float = 0.02, whiff_penalty: float = 0.02,
                 l2_obs: bool = True,
                 diversity_bonus: float = 1.0,
                 pool: list[str] | None = None,
                 cpu_governor: bool = True,
                 entity_obs: bool = False,
                 intent_mode: bool = False,
                 match_episodes: bool = False,
                 n_intents: int = 8,
                 stun_lock: bool = False,
                 y_obs: bool = False,
                 hitbox_obs: bool = False,
                 shape_events: bool = False,
                 time_penalty: float = 0.0,
                 allow_spam: bool = False,
                 skip_scenes: bool | None = None,
                 ai_role: int = 0,
                 want_pixels: bool = True):
        super().__init__()
        self.instance = instance
        self.sess = sess or BridgeSession(mode="1p", instance=instance)
        self.ai_role = int(ai_role)
        self.want_pixels = bool(want_pixels)
        self.speed = speed
        self.step_frames = step_frames
        self.max_steps = max_steps
        self.repeat_penalty = repeat_penalty
        self.whiff_penalty = whiff_penalty
        self.allow_spam = allow_spam
        # BEAUTIFUL-WIN shaping: winning with MORE distinct attack moves
        # pays extra (up to diversity_bonus when every attack type was used)
        self.diversity_bonus = diversity_bonus
        self._used_attacks: set = set()
        # pending attack window: steps left for the current attack to connect
        # (opponent bar drop). Expiring unresolved = WHIFF (penalty).
        self._whiff_left = 0
        self._whiff_open = False
        self._whiffs = 0
        self._attacks = 0
        self._latch_open = 0    # T5 damage-latch value at window open
        # curriculum pool: savestate names sampled per reset (lad1, lad2, ...)
        # None = always the r1 anchor
        self.pool = list(pool) if pool else None
        self._ep = 0
        self.moves = Moveset(PROJECT / "data" / "mame" / "movesets" / "haohmaru.yaml")
        # L2 obs (2026-11-12): old policies were trained on the 8d L1
        # obs — l2_obs=False keeps them watchable
        self.l2_obs = l2_obs
        # Entity obs (T11/A1, 2026-11-14): 25-dim x2 stack = 50 — uid-pointer
        # entity map + dual-channel distance + state flag matrix. OPT-IN:
        # every existing checkpoint is legacy-shaped.
        self.entity_obs = entity_obs
        self.y_obs = y_obs
        self.hitbox_obs = hitbox_obs
        self._uids: tuple[int, int] | None = None
        # C2 intent mode (design v3 §二): Discrete(8) tactical intents;
        # the reflex engine translates + overrides into base actions.
        # Requires entity_obs (the reflex gates read dx/flags).
        self.intent_mode = intent_mode
        assert not intent_mode or entity_obs,             "intent_mode requires entity_obs"
        self._last_dx = 0
        self._last_p2f = (0.0,) * 6
        self._last_char = 0
        # R3 review P0-1: hitbox channels are defined on the 54d R2 base —
        # a hitbox_obs=True / y_obs=False combination would build a 60d
        # stacked obs against a wrongly-declared space, so reject it at
        # init with an explicit error instead of dying mid-training.
        if entity_obs and hitbox_obs and not y_obs:
            raise ValueError(
                "hitbox_obs requires y_obs (the 5 Hitbox channels are "
                "defined on the 54d R2 base; review P0-1); got "
                "hitbox_obs=True y_obs=False")
        self.shape_events = shape_events
        self.time_penalty = time_penalty
        self._latch_hwm = 0
        self._ev_ch = 0
        self._ev_aa = 0
        self._time_paid = 0.0
        self._threat_obs = 0
        self._threat_reach = 128.0
        if entity_obs:
            # dims follow the ACTUAL switch combination (review P0-1),
            # derived from the versioned schema (single source of truth):
            per_frame = frame_width(5 if hitbox_obs else 0, with_y=y_obs)
            obs_dim = stacked_size(per_frame)
            self.observation_space = spaces.Box(
                -1.0, 1.0, shape=(obs_dim,), dtype=np.float32)
        else:
            self.observation_space = spaces.Box(
                0.0, 1.0, shape=(14 if l2_obs else 8,), dtype=np.float32)
        self.action_space = (spaces.Discrete(n_intents) if intent_mode
                             else spaces.Discrete(12))
        self._prev = (1.0, 1.0)              # (p1_bar, p2_bar) ratios
        self._zero_streak = (0, 0)
        self._stack: list[np.ndarray] = []
        self._steps = 0
        self._last_action = -1
        self._streak = 0
        # T20: current pool state (mid-episode reload fallback) and a fresh
        # (v, frame) pair stashed when a scene wait/reload refreshed the dump
        self._state_name = "r1"
        self._fresh: tuple | None = None
        # T18/C3-next (user design 2026-11-15: "训练要完整"): the training
        # unit is a COMPLETE best-of-3 match — a round KO scores ±2 but no
        # longer terminates; the episode ends at 2 round wins/losses. Rounds
        # 2/3, damaged-HP states and non-spawn positions then occur
        # naturally inside the episode.
        self.match_episodes = match_episodes
        self.skip_scenes = skip_scenes if skip_scenes is not None else self.match_episodes
        # R2 (plan v4): intent-space size (legacy default 8 keeps V1/V2
        # checkpoints loadable; R2 training passes 9) + own-hitstun idle
        # lock (opt-in so legacy eval semantics stay untouched)
        self.n_intents = n_intents
        self.stun_lock = stun_lock
        self.y_obs = y_obs
        self._p1_base_hp = 128.0
        self._p2_base_hp = 128.0
        self._hp_calib_locked: bool = False
        self._last_p1_mem_hp: int | None = None
        self._last_p2_mem_hp: int | None = None
        self._last_dispatched_act = 0
        self._last_dispatched_mask = 0
        self._last_crouch_guard_active = False
        self._last_crouch_guard_active = False
        self._last_p1f: tuple = (0,) * 6
        if match_episodes:
            self.max_steps = max(self.max_steps, 6000)
            self._round_wins = 0
            self._round_losses = 0
            self._round_draws = 0
            self._round_scored = False
            self._round_steps = 0
            self._prev_tf: float | None = None
        self._speed_set = False
        # runtime CPU governor: each instance samples the machine load and
        # downshifts its own throttle_rate (speed -> 1) when the machine is
        # saturating; upshifts again when headroom returns
        self.cpu_governor = cpu_governor
        self._cur_rate = int(speed)
        self._cpu_samples: list[int] = []
        self.reader = BarReader()  # Reinitialized on episode reset; intra-match rounds inherit fixed base HP from table

    # ------------------------------------------------------------- helpers
    def _bars(self, frame) -> tuple[float, float]:
        """(p1, p2) HP bar ratios in [0, 1]; seam for unit-test fakes.
        Production path: BarReader (per-char stamina normalization +
        camera-zoom HUD-vanish hold). frame=None holds last reading."""
        if frame is None:
            return self._prev
        c1, c2 = count_bars(frame[2], frame[0], frame[1])
        return self.reader.read(c1, c2)

    def _scene_wait(self):
        """T20 (production crash 2026-11-16 @25k): mid-episode scene
        transitions (round-KO banner / TIME OVER / refill) despawn the
        entity structs — uid ptrs read 0x0 for hundreds of frames, longer
        than resolve_entity_uids' 8-frame settle — and the RuntimeError
        killed the whole trainer. Advance frames WITHOUT input and probe
        the pointers until entities return; returns ((p1, p2), v, frame)
        with a FRESH dump, or None when the budget is exhausted."""
        for _ in range(SCENE_WAIT_CALLS):
            v, frame = self.sess.call("action",
                                      step_frames=max(self.step_frames, 6),
                                      want_pixels=True)
            p1 = self.sess.call("read_mem", P1UID_LOC, 4)
            p2 = self.sess.call("read_mem", P2UID_LOC, 4)
            if (0x102000 <= p1 <= 0x10F000 and 0x102000 <= p2 <= 0x10F000
                    and p1 != p2):
                return (p1, p2), v, frame
        return None

    def _uids_resolve(self, v, frame):
        """Resolve the uid pair, riding out mid-episode scene transitions;
        past the probe budget force a pool-state reload (reset()'s recovery
        ladder, mid-episode edition). Returns (uids, v, frame) — v/frame
        are FRESH whenever a scene wait or reload happened."""
        try:
            return resolve_entity_uids(self.sess), v, frame
        except RuntimeError:
            got = self._scene_wait()
            if got is not None:
                return got
            self.sess.ensure_active(state_name=self._state_name,
                                    settle_frames=40,
                                    skip_scenes=self.skip_scenes)
            v, frame = self.sess.call("action", step_frames=2,
                                      want_pixels=True)
            return resolve_entity_uids(self.sess), v, frame   # may raise

    def _sense(self, v: tuple[int, ...], frame) -> tuple[float, ...]:
        p1b, p2b = self._bars(frame)
        if self.entity_obs:
            p1_ptr = _field_be(v, P1UID_LOC, 4)
            p2_ptr = _field_be(v, P2UID_LOC, 4)
            if (self._uids is None
                    or len(self._uids) < 2
                    or p1_ptr != self._uids[0]
                    or p2_ptr != self._uids[1]):
                # uid canary drifted (entity relocation OR a scene
                # transition hiding them) — re-resolve, riding scenes out
                self._uids, v, frame = self._uids_resolve(v, frame)
                p1b, p2b = self._bars(frame)   # scene may have moved the bars
                self._fresh = (v, frame)
            # Authoritative WRAM entity health: ground truth directly from game engine memory.
            # Contract: reads uid + E_HEALTH (0xBB), which is the 1-byte unsigned main logical health.
            # (Note: uid + 0xBC is a 2-byte signed pending delta during hitstun; main health 0xBB updates
            # continuously as damage is absorbed, providing stable non-lagging logical health without
            # premature hitstun spikes).
            if self._uids and len(self._uids) >= 2:
                h1 = _field_be(v, self._uids[0] + E_HEALTH, 1)
                h2 = _field_be(v, self._uids[1] + E_HEALTH, 1)
                # Calibration window:
                # Active strictly while reader._n < CALIB_FRAMES.
                # Once reader._n reaches CALIB_FRAMES, calibration locks permanently for the round.
                if self.reader._n >= self.reader.CALIB_FRAMES:
                    self._hp_calib_locked = True

                if not self._hp_calib_locked:
                    if h1 > self._p1_base_hp:
                        self._p1_base_hp = float(h1)
                    if h2 > self._p2_base_hp:
                        self._p2_base_hp = float(h2)

                # Authoritative WRAM health ratio with pixel bar safety net (when pixels enabled):
                if self.want_pixels and h1 == 0 and p1b > 0.02:
                    p1b_use = p1b
                else:
                    p1b_use = min(max(float(h1) / self._p1_base_hp, 0.0), 1.0)

                if self.want_pixels and h2 == 0 and p2b > 0.02:
                    p2b_use = p2b
                else:
                    p2b_use = min(max(float(h2) / self._p2_base_hp, 0.0), 1.0)
                p1b, p2b = p1b_use, p2b_use
            feats = entity_features(v, self._uids[0], self._uids[1],
                                    p1b, p2b, y_obs=self.y_obs,
                                    hitbox_obs=self.hitbox_obs,
                                    p2_char_name=self._state_name)
            self._last_p1f = tuple(feats[14:20])
            return feats
        t = min(_field(v, A_TIMER), 0x99)
        cam = _field(v, A_CAM, 2)
        base = (max(min(p1b, 1.0), 0.0), max(min(p2b, 1.0), 0.0),
                (0x99 - t) / 0x99, cam / 65535.0)
        if self.l2_obs:
            return base + l2_features(v)
        return base

    def _obs(self, feat: np.ndarray) -> np.ndarray:
        self._stack.append(feat)
        self._stack = self._stack[-2:]
        while len(self._stack) < 2:
            self._stack.insert(0, feat)
        return np.concatenate(self._stack)

    def _tap(self, mask: int, press: int = 4, settle: int = 2):
        self.sess.call("press", role=self.ai_role, mask=mask, press_frames=press,
                       wait_frames=settle)
        return self.sess.call("action", step_frames=self.step_frames,
                              want_pixels=self.want_pixels)

    def _jump_mask(self) -> int:
        """R2 directional jump (review fix: the jump INTENT reuses A_JUMP;
        the direction is derived from dx at dispatch). Far = jump-in
        (UP+toward), inside poke range = jump away (UP+away), else neutral.
        LEGACY PATHS (non-entity / direct-mode) keep the historical pure-UP
        jump — the directional feature is R2 intent+entity only."""
        if not (self.intent_mode and self.entity_obs):
            return MSK_UP
        from mame_reflex import jump_mask_for
        return jump_mask_for(self._last_dx, self._last_char)

    def _macro(self, name: str):
        facing = (self._last_dx >= 0)
        for dm, bm, pf, gap in self.moves.get(name).actions(facing):
            self.sess.call("press", role=0, mask=dm | bm, press_frames=pf,
                           wait_frames=gap)
        return self.sess.call("action", step_frames=max(self.step_frames, 4),
                              want_pixels=self.want_pixels)

    # ----------------------------------------------------------- gym API
    def _get_state_char_id(self, state_name: str | None = None) -> int:
        name = state_name or getattr(self, "_state_name", "haowmaru")
        from mame_hitbox import normalize_char_name, SS2_CHAR_ID_MAP
        canon = normalize_char_name(name)
        name_to_id = {v: k for k, v in SS2_CHAR_ID_MAP.items()}
        return name_to_id.get(canon, 0)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if not self._speed_set and self._cur_rate != 1:
            self.sess.call("set", "throttle_rate", str(self._cur_rate))
            self._speed_set = True
        state = "r1"
        if self.pool:
            state = self.pool[self._ep % len(self.pool)]
            self._ep += 1
        self._state_name = state
        self._last_char = self._get_state_char_id(state)
        self._p1_base_hp = 128.0
        self._p2_base_hp = CHAR_MAX_HP_TABLE.get(state, 128.0)
        self._hp_calib_locked = False
        self.reader = BarReader()  # Reinitialized on episode reset; intra-match rounds inherit fixed base HP from table
        self._last_dispatched_act = 0
        self._last_dispatched_mask = 0
        self._last_crouch_guard_active = False
        # short settle: start controlling ASAP — an AFK walk-back during the
        # ~250f refill window can DIE vs strong CPUs (lad2 evidence). Survival
        # gating uses the pixel bar (refill animation is visible on it).
        ok, hp1, _hp2, _t = self.sess.ensure_active(
            state_name=state, settle_frames=40,
            skip_scenes=self.skip_scenes)
        if self.entity_obs:
            self._uids = resolve_entity_uids(self.sess)
        v, frame = self.sess.call("action", step_frames=2, want_pixels=True)
        sens = self._sense(v, frame)
        p1b, p2b = (sens[2], sens[3]) if self.entity_obs else sens[:2]
        if p1b < 0.10:                     # dead or refill not visible: retry
            ok, hp1, _hp2, _t = self.sess.ensure_active(state_name=state,
                                                        settle_frames=40)
            v, frame = self.sess.call("action", step_frames=2,
                                      want_pixels=True)
            sens = self._sense(v, frame)
            p1b, p2b = (sens[2], sens[3]) if self.entity_obs else sens[:2]
        if p1b < 0.10 and state != "r1":
            # last resort: fall back to the r1 anchor instead of crashing the
            # whole training run on one stale pool state
            ok, hp1, _hp2, _t = self.sess.ensure_active(state_name="r1",
                                                        settle_frames=40)
            v, frame = self.sess.call("action", step_frames=2,
                                      want_pixels=True)
            sens = self._sense(v, frame)
            p1b, p2b = (sens[2], sens[3]) if self.entity_obs else sens[:2]
        if p1b < 0.10:
            raise RuntimeError(f"env reset: no live round in {state} "
                               f"(bar_p1={p1b:.2f})")
        self._prev = (p1b, p2b)
        self._zero_streak = (0, 0)
        self._stack = []
        self._steps = 0
        self._last_action = -1
        self._streak = 0
        self._whiff_left = 0
        self._whiff_open = False
        self._whiffs = 0
        self._attacks = 0
        if self._fresh is not None:       # sense() scene-wait refreshed the dump
            v, frame = self._fresh
            self._fresh = None
        self._last_v = v
        self._latch_open = _field(v, T5_DAMAGE_LATCH)
        # R3 shaping state (review P2): latch high-water + per-episode
        # event/threat/time counters; threat bound from this round's
        # opponent identity (pool state name)
        self._latch_hwm = self._latch_open
        self._ev_ch = 0
        self._ev_aa = 0
        self._time_paid = 0.0
        self._threat_obs = 0
        self._threat_reach = float(get_max_threat_reach(self._state_name))
        if self.entity_obs:
            self._last_dx = int(sens[0] * 512)
            self._last_p2f = tuple(sens[8:14])
        if self.match_episodes:
            self._round_wins = self._round_losses = self._round_draws = 0
            self._round_scored = False
            self._round_steps = 0
            self._prev_tf = None
        self._used_attacks = set()
        feat = np.array(sens, dtype=np.float32)
        return self._obs(feat), {"p1": round(p1b * 128), "p2": round(p2b * 164)}

    def _cpu_load(self) -> int:
        import ctypes as _ct
        k32 = _ct.windll.kernel32

        idle1, kern1, user1 = (_ct.c_ulonglong(), _ct.c_ulonglong(),
                               _ct.c_ulonglong())
        k32.GetSystemTimes(_ct.byref(idle1), _ct.byref(kern1),
                           _ct.byref(user1))
        time.sleep(0.3)
        idle2, kern2, user2 = (_ct.c_ulonglong(), _ct.c_ulonglong(),
                               _ct.c_ulonglong())
        k32.GetSystemTimes(_ct.byref(idle2), _ct.byref(kern2),
                           _ct.byref(user2))
        d_idle = idle2.value - idle1.value
        d_total = ((kern2.value - kern1.value)
                   + (user2.value - user1.value))
        return int(100 * (1 - d_idle / max(d_total, 1)))

    def _govern(self) -> None:
        """Sample machine load every ~30s; >70% twice -> downshift a rate;
        <40% -> climb back toward the configured speed."""
        if self._steps % 30 != 0 or self._steps < 30:
            return
        load = self._cpu_load()          # ~0.3s pause, amortized
        self._cpu_samples.append(load)
        if len(self._cpu_samples) >= 2:
            avg = sum(self._cpu_samples[-2:]) / 2
            if avg > 70 and self._cur_rate > 1:
                self._cur_rate -= 1
                self.sess.call("set", "throttle_rate", str(self._cur_rate))
                print(f"[governor] CPU {avg:.0f}% -> rate {self._cur_rate}",
                      flush=True)
            elif avg < 40 and self._cur_rate < int(self.speed):
                self._cur_rate += 1
                self.sess.call("set", "throttle_rate", str(self._cur_rate))
                print(f"[governor] CPU {avg:.0f}% -> rate {self._cur_rate}",
                      flush=True)

    def step(self, action: int):
        self._steps += 1
        if self.cpu_governor:
            self._govern()
        sf = self.step_frames
        act = (reflex_action(action, self._last_dx, self._last_p2f,
                             self._last_char)
               if self.intent_mode else action)
        if self.intent_mode and not self.allow_spam:
            # C2 anti-spam (user spectate: within-round degradation to
            # light-slash spam — the reflex owns spacing resets now)
            sub = anti_spam(act, self._streak, self._last_dx,
                            self._last_p2f)
            if sub is not None:
                act = sub
        # R3 whiff guard (plan §二B1, review-scope): an airborne attack
        # dispatched beyond the heavy-slash tip + margin would whiff the
        # air slash — suppress to idle (drift) BEFORE the jump-slash
        # dispatch. Ground attacks keep translate()'s range gates.
        # R2 air override (probe 2026-11-17: the neutral-air flag family
        # 0x0006/0x0008/0x0009 leaves the word the moment an air attack
        # starts — 0x0103 family — so gate on the ATTACK action, not the
        # flag, and let A_JUMPSLASH's own two-state dispatch find the air)
        if (self.intent_mode and self._last_p1f[0] > 0
                and act in ATTACK_ACTIONS):
            sub = suppress_far_air(act, abs(self._last_dx), True)
            act = sub if sub is not None else A_JUMPSLASH
        # R2 opt-in own-hitstun lock (SFAgents animation-lock lesson; legacy
        # eval semantics untouched — default False)
        if self.stun_lock and self._last_p1f[1] > 0:
            act = A_IDLE
        mask = 0
        crouch_guard_active = False
        if act == A_IDLE:
            v, frame = self.sess.call("action", step_frames=sf, want_pixels=self.want_pixels)
        elif act in (A_WL, A_WR):
            away_act = A_WL if self._last_dx > 0 else A_WR
            away_mask = MSK_LEFT if self._last_dx > 0 else MSK_RIGHT
            toward_mask = MSK_RIGHT if self._last_dx > 0 else MSK_LEFT

            mask = MSK_LEFT if act == A_WL else MSK_RIGHT
            # Smart Crouch Guard (Down-Back):
            # Only applies when the agent is actually moving AWAY (retreating/guarding),
            # the policy requested guard (action == 7), and the opponent is grounded.
            # When opponent is airborne, plain away_mask stand-guards jump-ins.
            # If reflex overrode guard into an approach (_toward), act != away_act,
            # so it is NOT a guard, receives NO MSK_DOWN, and is NOT flagged as crouch guard.
            is_grounded_p2 = (not self._last_p2f or self._last_p2f[0] == 0)
            if self.intent_mode and action == 7 and act == away_act and is_grounded_p2:
                mask |= MSK_DOWN
                crouch_guard_active = True
            v, frame = self.sess.call("action", dir_mask=mask, press_frames=sf,
                                      step_frames=sf, want_pixels=self.want_pixels)
        elif act == A_JUMP:
            mask = self._jump_mask()
            v, frame = self._tap(mask, press=6, settle=0)
        elif act == A_JAB:
            mask = MSK_A
            v, frame = self._tap(mask)
        elif act == A_HEAVY:
            mask = MSK_B
            v, frame = self._tap(mask)
        elif act == A_KICK:
            mask = MSK_C
            v, frame = self._tap(mask)
        elif act == A_CROUCH:
            mask = MSK_DOWN | MSK_A
            v, frame = self._tap(mask, press=6)
        elif act == A_UPPERCUT:
            v, frame = self._macro("uppercut")
        elif act == A_RUSH:
            v, frame = self._macro("rush")
        elif act == A_FIREBALL:
            v, frame = self._macro("fireball")
        elif act == A_SAKE:
            v, frame = self._macro("sake")
        elif act == A_JUMPSLASH:
            # 方案A two-state dispatch (probe-verified): airborne -> slash
            # (MSK_A produced air-attack word 0x0103), ground -> start the
            # jump (UP), no whiff window either way
            if self._last_p1f[0] > 0:
                mask = MSK_A
                v, frame = self._tap(mask)
            else:
                mask = MSK_UP
                v, frame = self._tap(mask, press=6, settle=0)
        else:
            raise ValueError(f"bad action {act}")

        self._last_dispatched_act = act
        self._last_dispatched_mask = mask
        self._last_crouch_guard_active = crouch_guard_active
        self._last_v = v

        sens = self._sense(v, frame)
        if self._fresh is not None:       # scene wait/reload refreshed the dump
            v, frame = self._fresh
            self._fresh = None
        if self.entity_obs:
            p1b, p2b = sens[2], sens[3]
            tf = sens[23]                      # timer norm (BE channel)
        else:
            p1b, p2b, tf, cf = sens[:4]
        prev_p1, prev_p2 = self._prev
        dealt = max(prev_p2 - p2b, 0.0)
        taken = max(prev_p1 - p1b, 0.0)
        if p2b > prev_p2 + 0.02:              # refill/anomaly guard
            dealt = 0.0
        if p1b > prev_p1 + 0.02:
            taken = 0.0
        reward = dealt - taken                # full bar = 1.0 of damage
        # A3 reward reconciliation: every mutation below is mirrored into
        # an explicit component; reward == sum(comps) is an invariant the
        # tests assert (Task 3). damage_taken is stored as its (negative) contribution.
        comps = {"damage_dealt": dealt, "damage_taken": -taken,
                 "counter_event": 0.0, "anti_air_event": 0.0,
                 "round_result": 0.0, "fast_bonus": 0.0,
                 "time_cost": 0.0, "repeat_penalty": 0.0,
                 "whiff_penalty": 0.0, "diversity_bonus": 0.0}

        # whiff detection: an open attack window closes either by CONNECTING
        # (opponent bar dropped this step, or the T5 damage latch moved —
        # the latch reads through the camera zoom that blinds the bar) or by
        # expiring (penalty)
        latch = _field(v, T5_DAMAGE_LATCH)
        if self._whiff_open:
            self._whiff_left -= 1
            if whiff_connected(dealt, latch, self._latch_open):
                self._whiff_open = False          # connected
            elif self._whiff_left <= 0:
                reward -= self.whiff_penalty
                comps["whiff_penalty"] -= self.whiff_penalty
                self._whiffs += 1
                self._whiff_open = False

        # R3 event shaping (review P2): one damage event per latch
        # high-water rise; overlap labels pay the single higher reward
        if self.shape_events:
            ev_r, ev_kind, self._latch_hwm = hit_event_reward(
                latch, self._latch_hwm, self._last_p2f)
            if ev_kind == "counter":
                self._ev_ch += 1
                reward += ev_r
                comps["counter_event"] += ev_r
            elif ev_kind == "anti_air":
                self._ev_aa += 1
                reward += ev_r
                comps["anti_air_event"] += ev_r
        # R3 threat observation (LOG-ONLY, review P1-2): counts how often
        # the distance heuristic + punishable-family condition holds; it
        # NEVER overrides the action chosen above
        if self.intent_mode and threat_guard_probe(
                abs(self._last_dx), self._last_p2f, self._threat_reach):
            self._threat_obs += 1

        # anti-spam: repeating one action gets progressively costlier
        if act == self._last_action:
            self._streak += 1
        else:
            self._streak = 0
        self._last_action = act
        if self._streak >= 3:
            pen = self.repeat_penalty * min(self._streak - 3, 10)
            reward -= pen
            comps["repeat_penalty"] -= pen

        if act in ATTACK_ACTIONS:
            self._used_attacks.add(act)
            self._attacks += 1
            if self._whiff_open:                  # superseded before connecting
                reward -= self.whiff_penalty
                comps["whiff_penalty"] -= self.whiff_penalty
                self._whiffs += 1
            self._whiff_left = (WHIFF_WINDOW_PROJ if act == A_FIREBALL
                                else WHIFF_WINDOW_MELEE)
            self._latch_open = latch
            self._whiff_open = True
        self._prev = (p1b, p2b)
        # R3 time penalty (plan §二C3): per DECISION step; coefficient
        # calibrated from the diag step distribution BEFORE ignition
        if self.time_penalty > 0:
            reward -= self.time_penalty
            comps["time_cost"] -= self.time_penalty
            self._time_paid += self.time_penalty
        if self.entity_obs:
            self._last_dx = int(sens[0] * 512)
            self._last_p2f = tuple(sens[8:14])
        p1_hp = (_field_be(v, self._uids[0] + E_HEALTH, 1)
                 if (self._uids and len(self._uids) >= 2) else round(p1b * 128))
        p2_hp = (_field_be(v, self._uids[1] + E_HEALTH, 1)
                 if (self._uids and len(self._uids) >= 2) else round(p2b * 164))
        if p1_hp <= 0 and p1b > 0.02:
            p1_hp = max(1, round(p1b * 128))
        if p2_hp <= 0 and p2b > 0.02:
            p2_hp = max(1, round(p2b * 164))
        # Zero-streak tracking: require BOTH pixel empty AND memory HP zero
        # to prevent rage flash / red-bar false KO
        zs1 = self._zero_streak[0] + 1 if (p1b <= 0.005 and p1_hp <= 0) else 0
        zs2 = self._zero_streak[1] + 1 if (p2b <= 0.005 and p2_hp <= 0) else 0
        self._zero_streak = (zs1, zs2)
        if self.match_episodes:
            # match-scoped episode (user design 2026-11-15: "训练要完整"):
            # a round KO scores ±2 but does NOT terminate — the episode is
            # a full best-of-3 match, ending at 2 round wins/losses. Rounds
            # 2/3, damaged-HP states and non-spawn positions occur naturally.
            self._round_steps += 1
            if not self._round_scored and (zs2 >= 2 or zs1 >= 2):
                self._round_scored = True
                round_age = self._round_steps
                self._round_steps = 0
                # P0-02: 统一判定契约，双方同时倒地优先判定相杀 DRAW
                if (zs1 >= 2 and zs2 >= 2) or (p1_hp <= 0 and p2_hp <= 0 and (zs1 >= 1 or zs2 >= 1)):
                    self._round_draws += 1
                    comps["round_result"] += 0.0
                elif zs2 >= 2 and p2_hp <= 0:
                    self._round_wins += 1
                    reward += 2.0
                    comps["round_result"] += 2.0
                    if round_age < 120:
                        reward += 0.5         # fast round (real age)
                        comps["fast_bonus"] += 0.5
                elif zs1 >= 2 and p1_hp <= 0:
                    self._round_losses += 1
                    reward -= 2.0
                    comps["round_result"] -= 2.0
                else:
                    self._round_scored = False
            # BUG-17 fix (2026-11-18, user spectate): two defects in the
            # time-over judge. (a) DRAIN GUARD: the timer byte reads ~0 for
            # the first frames after a savestate load / round reload, so the
            # 0x01 -> 0x99 wrap detector fired phantom rounds 21-30 steps in;
            # a genuine full drain takes ~900 decision steps, so require the
            # round to be at least 300 steps old. (b) DIRECTION was inverted:
            # `p2b >= p1b -> round_wins` awarded the round to the side with
            # LESS health, paying the turtle-to-time-over strategy +2 for
            # losing rounds (the retreat-45% / attack-collapse behavior was
            # partly farmed on this fake signal).
            if (not self._round_scored and self._round_steps >= 300
                    and self._prev_tf is not None
                    and self._prev_tf > 0.95 and tf < 0.05):
                # timer wrapped 0x01 -> 0x99: TIME OVER — the higher bar wins
                self._round_scored = True
                self._round_steps = 0
                if p1b > p2b:                     # higher bar wins, ours
                    self._round_wins += 1
                    reward += 2.0
                    comps["round_result"] += 2.0
                else:                             # opponent higher (or tie)
                    self._round_losses += 1
                    reward -= 2.0
                    comps["round_result"] -= 2.0
            if self._round_scored:
                # Next round is only live if the loser has substantially refilled
                # In SS2, loser always refills to full (> 0.60), while winner keeps leftover (> 0.05)
                # Requiring p1b > 0.005 and p2b > 0.005 caused phantom resets on dead-body sprite flickers!
                both_substantial = (p1b > 0.40 and p2b > 0.05) or (p2b > 0.40 and p1b > 0.05)
                if both_substantial and zs1 == 0 and zs2 == 0:
                    self._round_scored = False    # next round is genuinely live
            self._prev_tf = tf                # time-over wrap detection
            terminated = bool(self._round_wins >= 2
                              or self._round_losses >= 2)
            rounds = (self._round_wins, self._round_losses)
        else:
            terminated = bool(zs1 >= 2 or zs2 >= 2 or tf >= 0.999)
            if (zs1 >= 2 and zs2 >= 2) or (p1_hp <= 0 and p2_hp <= 0 and (zs1 >= 1 or zs2 >= 1)):
                comps["round_result"] += 0.0
            elif zs2 >= 2 and p2_hp <= 0:
                bonus = 0.5 if self._steps < 120 else 0.0
                reward += 2.0 + bonus
                comps["round_result"] += 2.0
                comps["fast_bonus"] += bonus
                if self.diversity_bonus > 0:
                    div = len(self._used_attacks) / len(ATTACK_ACTIONS)
                    reward += self.diversity_bonus * div
                    comps["diversity_bonus"] += self.diversity_bonus * div
            elif zs1 >= 2 and p1_hp <= 0:
                reward -= 2.0                     # loss
                comps["round_result"] -= 2.0
            rounds = (0, 0)
        truncated = bool(self._steps >= self.max_steps and not terminated)
        feat = np.array(sens, dtype=np.float32)
        return self._obs(feat), float(reward), terminated, truncated, {
            "p1": round(p1b * 128), "p2": round(p2b * 164),
            "p1_hp": p1_hp, "p2_hp": p2_hp,
            "dispatched_act": self._last_dispatched_act,
            "dispatched_mask": self._last_dispatched_mask,
            "crouch_guard_active": self._last_crouch_guard_active,
            "steps": self._steps, "whiffs": self._whiffs,
            "attacks": self._attacks, "used": len(self._used_attacks),
            "rounds": rounds,
            "threat_obs": self._threat_obs,
            "ev_ch": self._ev_ch, "ev_aa": self._ev_aa,
            "time_paid": round(self._time_paid, 4),
            "reward_components": dict(comps)}

    def close(self):
        try:
            self.sess.bridge.quit()
            self.sess.bridge.close()
        except Exception:  # noqa: BLE001
            pass
