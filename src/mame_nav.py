"""Menu navigation for samsho2 (deterministic round-1 anchoring).

Design (settled 2026-11-05 after spam-nav experiments):
  * freeplay DIP set early replaces coin injection (IPT_COIN1 unreachable)
  * boot ~1800f to title; START re-pressed every 600f (title window varies)
  * A pressed every 30f: skips dialogue, picks Haohmaru, confirms
  * FIRST timer==BCD-0x99 freeze after START = round-1 freeze (fresh HP) —
    the attract demo only starts much later, and we've left attract by then.
  * anchor = save_state("r1") at that freeze; ensure_active() loads it and
    burns the freeze (~156f) so callers start at an active fresh round.
"""
from __future__ import annotations

import time
from pathlib import Path

from mame_screen import grab_png
from mame_types import DIR_MASKS, MSK_A, ROLE_START

TIMER_ADDR = 0x100AC5
PROJECT_LOGDIR = Path(__file__).resolve().parent.parent / "data"
# entity-map literals (T11 compendium; kept local to avoid a mame_gym
# import cycle — mame_gym imports mame_client which imports mame_nav)
P1UID_LOC, P2UID_LOC = 0x100A46, 0x100A4A
E_HEALTH = 0xBB


def round_is_live(h1: int, h2: int) -> bool:
    """Flexible live-round gate (user's three-case taxonomy, 2026-11-15):
    a saved state may be (1) pre-start [healths read 0 until initialized],
    (2) started [countdown running], or (3) already fighting [damage taken
    / someone mid-air]. Cases 2-3 accept immediately — ANY positive health
    on both entities counts as live; only case 1 needs A-spam waiting."""
    return h1 > 0 and h2 > 0


def _timer_byte(v: tuple[int, ...]) -> int:
    off = TIMER_ADDR - 0x100000
    idx = off // 4
    if idx >= len(v):
        return -1  # layout mismatch (compact CONFIG) — caller decides
    return (v[idx] >> ((off % 4) * 8)) & 0xFF


def _hp_bytes(v: tuple[int, ...]) -> tuple[int, int]:
    """TRUE HP addresses: P1 0x104B78 u8, P2 0x105E98 u8 (128-scale).
    P2 history: 0x103132 FALSIFIED 2026-11-11 (polluted: stuck at the
    opponent's stamina value in CPU fights; drove overnight rejection
    loops) -> T5 differencing verified 0x105E98 frame-locked with the
    pixel bar. The 0x10134E/0x101350 mirrors are also FALSIFIED.
    Per-char stamina: fresh Haohmaru = 0x80 (P1 selection is fixed)."""
    def byte(a):
        off = a - 0x100000
        if off // 4 >= len(v):
            return -1  # layout mismatch (compact CONFIG) — caller decides
        return (v[off // 4] >> ((off % 4) * 8)) & 0xFF
    return byte(0x104B78), byte(0x105E98)


def reach_round1_anchor(bridge, *, mode: str = "2p",
                        state_name: str = "r1",
                        max_frames: int = 12000) -> tuple[bool, int, int, int, float]:
    """Freeplay -> boot -> self-healing START/A loop -> VERIFIED round-1 anchor.

    Catches timer==BCD-0x99 freezes inside a window after each START press,
    then VERIFIES by loading the candidate and burning the freeze: a fresh
    round refills both HP (2p mirror: A0/A0). Demo freezes fail verification
    and are discarded; START-during-demo returns to the title, so the loop
    self-heals. Returns (ok, hp1, hp2, timer, seconds); verified ACTIVE state
    saved as  (loaders start in-round immediately).
    """
    t0 = time.time()
    bridge.set("field", "DSW:64:1")              # freeplay before game init
    for _ in range(125):                         # ~1500f boot to title
        bridge.action(step_frames=12)
    since_start = 10 ** 9
    for i in range(max_frames):
        # cadence 2026-11-11: boot lands on the HOW-TO screen and the title
        # times out into the attract demo within ~30s — a START every ~900f
        # (phase probe: compact double-START reaches a real round; the old
        # 600-iter (~5min) gap always landed in the demo loop)
        if i % 30 == 0:
            bridge.press(role=2, mask=0x01, press_frames=8, wait_frames=2)
            since_start = 0
        if mode == "2p" and i % 30 == 15:
            bridge.press(role=2, mask=0x04, press_frames=8, wait_frames=2)
        # A-spam ONLY right after START (menus/dialogue/character select).
        # Beyond that we are likely mid-fight: blind A-mashing gets P1 killed
        # and pushes the game into the attract demo, whose round-start freeze
        # ALSO satisfies t==0x99 but replays a scripted fight (verify reads
        # deterministic garbage, e.g. hp1=0x0 hp2=0x8c, forever).
        if since_start <= 330 and i % 30 == 15:
            bridge.press(role=0, mask=0x10, press_frames=6, wait_frames=2)
        if mode == "2p" and since_start <= 330 and i % 30 == 0:
            bridge.press(role=1, mask=0x10, press_frames=6, wait_frames=2)
        if i % 30 == 20:
            bridge.action(step_frames=8)
        v, _ = bridge.action(step_frames=2)
        since_start += 2
        if i % 600 == 0:
            print(f'  nav f{i}: t={_timer_byte(v):#x} since_start={since_start}',
                  flush=True)
        # window 2026-11-11: since_start resets every 30 iters now, so
        # the old >=200 floor never triggered; the demo filter is the
        # verify itself (hp1==0x80), not this window
        if _timer_byte(v) == 0x99 and 8 <= since_start <= 2600:
            bridge.save_state(state_name + "_cand")
            bridge.load_state(state_name + "_cand")
            hp1 = hp2 = None
            # burn the freeze while WALKING BACK (P1 spawns left, CPU right):
            # a standing P1 eats lvl4-CPU combos during the ~400f burn and the
            # candidate gets rejected (hp1 low/0) -> rejection loop
            for _ in range(150):
                v, _ = bridge.action(dir_mask=0x04, step_frames=2)
                if _timer_byte(v) != 0x99:
                    break
            # HP refill is ANIMATED: keep advancing ~250f past activation
            # before reading, otherwise stale values cause false rejection
            for _ in range(125):
                v, _ = bridge.action(dir_mask=0x04, step_frames=2)
            hp1, hp2 = _hp_bytes(v)
            try:                      # verify forensics (phase-probe dir)
                from mame_screen import grab_png as _gp
                _verify_n = globals().get("_verify_n", 0) + 1
                globals()["_verify_n"] = _verify_n
                _gp(bridge, Path(PROJECT_LOGDIR) / "nav_phases"
                    / f"verify_{_verify_n:03d}_hp1{hp1:02x}_hp2{hp2:02x}.png")
            except Exception:  # noqa: BLE001
                pass
            print(f"  verify({mode}): hp1={hp1:#x} hp2={hp2:#x} "
                  f"t={_timer_byte(v):#x}", flush=True)
            if mode == "2p" and hp1 == 0x80 and hp2 == 0x80:
                bridge.save_state(state_name)   # verified ACTIVE state
                return True, hp1, hp2, _timer_byte(v), time.time() - t0
            if mode == "1p" and hp1 == 0x80:
                # stability check: fresh round keeps P1 full for ~60 frames
                stable = True
                for _ in range(10):
                    v, _ = bridge.action(step_frames=6)
                    h1c, _h2 = _hp_bytes(v)
                    if h1c != 0x80:
                        stable = False
                        break
                if stable:
                    bridge.save_state(state_name)
                    return True, hp1, hp2, _timer_byte(v), time.time() - t0
            # rejected. hp1==0x0 = demo-loop signature (scripted P1): burst
            # STARTs to force the demo back to the title, then keep polling.
            if hp1 == 0x0:
                print("  demo-loop escape: START burst", flush=True)
                for _ in range(3):
                    bridge.press(role=2, mask=0x01, press_frames=8,
                                 wait_frames=2)
                    bridge.action(step_frames=20)
                since_start = 0
    return False, None, None, None, time.time() - t0


def ensure_active_round(bridge, *, state_name: str = "r1",
                        max_frames: int = 400,
                        settle_frames: int = 300,
                        skip_scenes: bool = False) -> tuple[bool, int, int, int]:
    """load state -> burn the freeze -> wait for HP refill to settle.

    The HP byte ANIMATES up from 0 after activation (~250f) — reading at the
    live moment returns 0 (2026-11-08 lad2 crash). Wait until the byte is
    stable for ~10 consecutive reads and alive, walking back to survive.
    Returns (ok, hp1, hp2, timer); ok requires alive.

    skip_scenes (T18 pool states): story / VS / boss-intro scenes are
    A-skippable — spam A (and poll entity health) until the round is LIVE
    (both health bytes >= 0x60) before the normal settle. Normal states
    exit this loop on the first poll with zero side effects."""
    # existence guard FIRST: machine:load of a missing file silently
    # "succeeds" (Lua pcall sees no error — 2026-11-06 trap) and the next
    # action dies on the socket with an opaque bridge error.
    state_file = (Path(bridge.proc.inst_dir) / "state" / "samsho2"
                  / f"{state_name}.sta")
    if not state_file.exists():
        raise RuntimeError(f"state '{state_name}' not found: {state_file}")
    bridge.load_state(state_name)
    if skip_scenes:
        frames = 0
        prev = (-1, -1)
        while frames < 3600:
            h1 = h2 = -1
            try:
                p1u = bridge.read_mem(P1UID_LOC, 4)
                p2u = bridge.read_mem(P2UID_LOC, 4)
                if (0x102000 <= p1u <= 0x10F000
                        and 0x102000 <= p2u <= 0x10F000):
                    h1 = bridge.read_mem(p1u + E_HEALTH, 0)
                    h2 = bridge.read_mem(p2u + E_HEALTH, 0)
            except Exception:  # noqa: BLE001
                pass                     # pre-init entity pointers: keep
            # flexible gate: both entities positive AND stable across two
            # consecutive polls (rejects the KO-banner refill animation,
            # accepts damaged mid-fight states instantly)
            if round_is_live(h1, h2) and (h1, h2) == prev:
                break                    # live
            prev = (h1, h2)
            bridge.press(role=0, mask=MSK_A, press_frames=4, wait_frames=20)
            frames += 24
        else:
            raise RuntimeError(f"scene-skip: '{state_name}' never reached a "
                               f"live round within {frames} frames")
    live = False
    for _ in range(max_frames // 2):
        v, _ = bridge.action(step_frames=2)
        if _timer_byte(v) != 0x99:
            live = True
            break
    last, stable = -1, 0
    hp1 = hp2 = 0
    for _ in range(settle_frames // 2):
        v, _ = bridge.action(dir_mask=DIR_MASKS["L"], step_frames=2)
        hp1, hp2 = _hp_bytes(v)
        if hp1 == last and hp1 > 0:
            stable += 1
            if stable >= 10:
                return True, hp1, hp2, _timer_byte(v)
        else:
            stable = 0
        last = hp1
    return bool(live and hp1 > 0), hp1, hp2, _timer_byte(v)


def grab_in_fight(bridge, path: Path) -> tuple:
    return grab_png(bridge, path)
