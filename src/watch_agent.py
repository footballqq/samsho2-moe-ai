"""Watch the trained agent play vs the CPU in a VISIBLE MAME window.

Real speed, real sound. The agent is Haohmaru (policy is character-specific);
pick the ladder opponent via the pool state (lad1..lad8).

Usage (venv python):
  .venv\\Scripts\\python.exe -I src\\watch_agent.py [opponent 1-14] [matches] [old|new] [det|stoch]

Or double-click  watch_agent.cmd  (opponent 1, 3 matches, old policy).
  3rd arg picks the policy: old = 195518 (pre-T5 det winner, 8-d obs),
  new = 20261112_071944 (T5 whiff-signal L2-obs, 14-d obs),
  div = 154224 (B-run diverse play, loses some opponents, 8-d obs),
  c3 = 20261115_082359 (T11 entity-obs intent policy, 50-d obs).
  4th arg picks the view: det = argmax (default — an undertrained policy
  may stand still; that is not a hang), stoch = sampled actions.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

from mame_protocol import BridgeError
from mame_features_schema import stacked_timer_index

# tag -> best.zip. "new" is the L2 retrain (20261112_071944); the earlier
# 20261111_011227 run is actually 8-d and must not be tagged "new".
# "div" = the B anti-spam run (20261110_154224): diverse mixed play, but
# it LOSES some opponents — the non-guaranteed-win viewing option.
# "c3" = the T11 entity-obs intent policy (20261115_082359, 50-d obs +
# Discrete(8) intent space).
POLICIES = {
    "old": PROJECT / "data" / "rl" / "ppo_smoke_20261108_195518" / "best.zip",
    "new": PROJECT / "data" / "rl" / "ppo_smoke_20261112_071944" / "best.zip",
    "div": PROJECT / "data" / "rl" / "ppo_smoke_20261110_154224" / "best.zip",
    "c3": PROJECT / "data" / "rl" / "ppo_smoke_20261115_082359" / "best.zip",
}


def obs_mode_for(model) -> dict:
    """Derive the env construction switches from the loaded policy itself
    (single source of truth — the tag never decides shapes; lesson of the
    three tag/model mismatches). Returns kwargs for SS2RoundEnv."""
    shape = tuple(model.observation_space.shape)
    if shape == (64,):
        # R3: hitbox-aware entity obs (32d frame x2 stack; defined on the
        # 54d R2 base — hitbox_obs implies y_obs, enforced by the env)
        return dict(entity_obs=True, l2_obs=True, intent_mode=True,
                    n_intents=9, y_obs=True, hitbox_obs=True)
    if shape == (54,):
        # R2: Y-channel entity obs (9-intent models; stun_lock is a
        # training-time switch — viewing keeps legacy semantics)
        return dict(entity_obs=True, l2_obs=True, intent_mode=True,
                    n_intents=9, y_obs=True)
    if shape == (50,):
        n = model.action_space.n
        return dict(entity_obs=True, l2_obs=True,
                    intent_mode=(n == 8))
    if shape == (14,):
        return dict(entity_obs=False, l2_obs=True)
    if shape == (8,):
        return dict(entity_obs=False, l2_obs=False)
    raise ValueError(f"unknown observation shape {shape}")


def play_match(env, model, *, proc_alive, deterministic=True,
               max_steps: int = 15000, reset: bool = True) -> list[str]:
    """One CONTINUOUS best-of-3 match (T9 v1): a single env.reset loads the
    opponent state (skip it with reset=False when the game is already live
    mid-ladder), then the GAME's own round flow runs — KO, banner, refill,
    next round — with no resets in between. Round wins/losses are counted
    from bar-zero events (latched until both bars refill, so one KO streak
    counts exactly once). First to 2 rounds ends the match. Window close /
    process exit = the documented stop path; alive proc + EOF re-raises."""
    lines: list[str] = []
    wins = losses = round_no = steps = 0
    armed = True                                   # round-end detector
    round_steps = 0    # BUG-17 fix: steps since the round went live — the
    # time-over verdict needs a drained timer (a genuine SS2 drain is ~900
    # decision steps); the timer byte reads ~0 right after a load/reload,
    # which used to fire phantom "WIN on time (21 steps)" rounds the user
    # caught live. Also the old verdict was DIRECTION-INVERTED: it counted
    # `opponent bar higher -> our win`, paying real losses as wins.
    prev_tf = None                                 # timer norm (time-over)
    try:
        if reset:
            obs, info = env.reset()
        else:
            obs, _r, _t, _tr, info = env.step(0)   # pick up the live game
        # Dynamic schema-derived timer index
        obs_dim = obs.shape[0] if hasattr(obs, "shape") else len(obs)
        if obs_dim in (50, 54, 64):
            tf_idx = stacked_timer_index(obs_dim // 2)
        elif getattr(env, "entity_obs", False):
            tf_idx = 48
        else:
            tf_idx = 2
        while wins < 2 and losses < 2 and steps < max_steps:
            a, _ = model.predict(obs, deterministic=deterministic)
            obs, r, term, trunc, info = env.step(int(a))
            steps += 1
            if armed:
                round_steps += 1
            p1r = info["p1"] / 128.0
            p2r = info["p2"] / 164.0
            try:
                tf = float(obs[tf_idx])
            except (TypeError, ValueError, IndexError):
                tf = None          # fake/compact obs: no timer channel
            if armed and p2r <= 0.02:              # opponent bar emptied: KO
                round_no += 1
                wins += 1
                armed = False
                lines.append(f"round {round_no}: WIN ({steps} steps)")
            elif armed and p1r <= 0.02:            # our bar emptied: KO
                round_no += 1
                losses += 1
                armed = False
                lines.append(f"round {round_no}: LOSS ({steps} steps)")
            elif (armed and round_steps >= 300 and prev_tf is not None
                  and prev_tf > 0.95 and tf < 0.05):
                # timer wrapped 0x01 -> 0x99: TIME OVER — the higher bar
                # wins (BUG-17: guard + direction fixed, see round_steps)
                round_no += 1
                armed = False
                if p1r > p2r:
                    wins += 1
                    lines.append(f"round {round_no}: WIN on time "
                                 f"({round_steps} steps)")
                else:
                    losses += 1
                    lines.append(f"round {round_no}: LOSS on time "
                                 f"({round_steps} steps)")
            elif not armed and p1r > 0.15 and p2r > 0.15:
                armed = True                       # next round is live
                round_steps = 0
            prev_tf = tf
    except BridgeError as e:
        if proc_alive():
            raise
        lines.append(f"MAME window closed or process exited during match "
                     f"— stopping ({e}).")
        return lines
    verdict = "WIN" if wins > losses else "LOSS"
    lines.append(f"match: {wins}-{losses} {verdict} ({steps} steps)")
    return lines


def wait_live_round(sess, *, max_polls: int = 120) -> bool:
    """T9-lite intermission (post-victory scene skip): tap A to skip story /
    VS screens and poll the flexible live gate (round_is_live — both entity
    healths positive AND stable across two polls, accepting damaged
    mid-fight states instantly). A-presses only fire when NOT live yet."""
    from mame_gym import E_HEALTH, resolve_entity_uids
    from mame_nav import round_is_live
    from mame_types import MSK_A
    prev = (-1, -1)
    for _ in range(max_polls):
        try:
            p1u, p2u = resolve_entity_uids(sess, max_settle=2)
            h1 = sess.call("read_mem", p1u + E_HEALTH, 0)
            h2 = sess.call("read_mem", p2u + E_HEALTH, 0)
            if round_is_live(h1, h2) and (h1, h2) == prev:
                return True
            prev = (h1, h2)
        except RuntimeError:
            pass                                   # pre-init / title: keep
        sess.call("press", role=0, mask=MSK_A, press_frames=4,
                  wait_frames=20)                  # ~24 frames per poll
    return False


def ladder_spectate(env, model, sess, *, matches: int, proc_alive,
                    deterministic: bool = True) -> list[str]:
    """T9-lite ladder run: watch consecutive matches in ONE continuous
    game — a won match flows naturally into the next opponent (A-spam skips
    the story/VS screens); a lost match stops the run (the continue screen
    needs a coin — out of scope). Each opponent's charID is reported."""
    from mame_gym import E_CHAR, resolve_entity_uids
    lines: list[str] = []
    env.reset()                                    # load the starting state
    done = 0
    while done < matches:
        if not wait_live_round(sess):
            lines.append("ladder: live round not detected — stopping.")
            break
        try:
            _p1u, p2u = resolve_entity_uids(sess, max_settle=4)
            c2 = sess.call("read_mem", p2u + E_CHAR, 0)
        except RuntimeError:
            c2 = -1
        lines.append(f"opponent {done + 1}: charID {c2:#04x}")
        try:
            for ln in play_match(env, model, proc_alive=proc_alive,
                                 reset=False, deterministic=deterministic):
                lines.append(ln)
        except BridgeError as e:
            if proc_alive():
                raise
            lines.append(f"stopping ({e})")
            break
        last = next((ln for ln in reversed(lines)
                     if ln.startswith("match")), "")
        if "LOSS" in last:
            lines.append("ladder: match lost — stopping (continue screen "
                         "out of scope).")
            break
        done += 1
    return lines


def parse_watch_args(argv: list[str]) -> tuple[str, int, str, str]:
    """Order-tolerant argument parsing: policy tags (old/new/div/c3) and
    views (det/stoch) are recognized keywords; the remaining positionals
    are opponent then matches. Defaults: opponent 1, matches 3, old, det."""
    pos: list[str] = []
    for a in argv:
        if a in ("det", "stoch") or a in POLICIES:
            continue
        pos.append(a)
    view = "stoch" if "stoch" in argv else "det"
    pol = next((a for a in argv if a in POLICIES), "old")
    opponent = pos[0] if pos else "1"
    matches = int(pos[1]) if len(pos) > 1 else 3
    return opponent, max(matches, 1), pol, view


def main(argv: list[str]) -> int:
    opponent, matches, pol, view = parse_watch_args(argv)
    # opponent may be a ladder number (lad<N>) or a pool state name
    # (haowmaru, wafu, ...) — the verified identity states live in the
    # watch instance dir.
    state = f"lad{opponent}" if opponent.isdigit() else opponent
    # policy selector: recognized keywords anywhere in the args (old/new/
    # div/c3), view det/stoch — see parse_watch_args above.

    from mame_client import BridgeSession
    from mame_gym import SS2RoundEnv
    from stable_baselines3 import PPO

    if pol not in POLICIES:
        print(f"[watch] unknown policy {pol!r} (use old|new)")
        return 1
    print(f"[watch] policy = {pol} ({POLICIES[pol].parent.name})")
    model = PPO.load(str(POLICIES[pol]), device="cpu")
    print(f"[watch] launching VISIBLE MAME window (real speed, sound)...")
    sess = BridgeSession(mode="1p", instance="watch", windowed=True)
    env = SS2RoundEnv(sess=sess, speed=1, pool=[state], max_steps=30000,
                      **obs_mode_for(model))
    print(f"[watch] opponent = {state}; watching {matches} ladder matches "
          f"(best of 3 each). Close the MAME window to stop.", flush=True)
    try:
        for ln in ladder_spectate(env, model, sess, matches=matches,
                                  proc_alive=lambda: sess.bridge.proc.alive(),
                                  deterministic=(view == "det")):
            print(f"[watch] {ln}", flush=True)
    except RuntimeError as e:
        print(f"[watch] {e}", flush=True)
        return 1
    finally:
        try:
            env.close()
        except Exception:
            pass  # MAME already gone — job object cleaned it up
    print("[watch] finished.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
