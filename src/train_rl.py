"""Overnight PPO trainer for SS2 (smoke-scale, single instance).

Usage (venv python):
  E:\\games\\SamuraiShodownII\\.venv\\Scripts\\python.exe -I src\\train_rl.py [steps]

Outputs:
  data\\rl\\ppo_smoke_<stamp]\\        model checkpoints (zip) + final
  logs\\rl_train_<stamp>.jsonl        periodic progress lines
  logs\\rl_train_<stamp>.log          tensorboard dir alongside
"""
from __future__ import annotations

import os as _os
_tlib = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), _os.pardir, '.venv', 'Lib', 'site-packages', 'torch', 'lib')
_os.environ['PATH'] = _tlib + _os.pathsep + _os.environ.get('PATH', '')
import torch  # FIRST: shm.dll init fails when loaded after numpy/MKL (WinError 1114)
import json
import sys
import time
from pathlib import Path
PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

from mame_gym import SS2RoundEnv  # noqa: E402
from stable_baselines3.common.callbacks import BaseCallback  # noqa: E402

STATE_SRC = PROJECT / "data" / "mame" / "instance" / "rl" / "state" / "samsho2"


def distribute_states(instance: str, states: list[str]) -> None:
    """Copy pool savestates (+r1) into a per-instance state dir."""
    import shutil
    dst = (PROJECT / "data" / "mame" / "instance" / instance
           / "state" / "samsho2")
    dst.mkdir(parents=True, exist_ok=True)
    for st in set(states) | {"r1"}:
        f = STATE_SRC / f"{st}.sta"
        if f.exists():
            shutil.copy2(f, dst / f"{st}.sta")


def make_env(rank: int, pool: list[str], repeat_penalty: float,
             whiff_penalty: float, diversity_bonus: float, speed: int,
             cpu_governor: bool = True, entity_obs: bool = False,
             intent_mode: bool = False, match_episodes: bool = False,
             n_intents: int = 8, stun_lock: bool = False,
             y_obs: bool = False,
             hitbox_obs: bool = False,
             shape_events: bool = False,
             time_penalty: float = 0.0,
             instance_prefix: str = "rl"):
    """Module-level env factory (cloudpickle-safe for SubprocVecEnv).

    Wrapped with single-retry resilience: a transient bridge failure rebuilds
    the session once; a second failure re-raises (SubprocVecEnv then stops the
    whole run — same as before, but one-off aborts no longer kill the night)."""
    def _init():
        inst = f"{instance_prefix}{rank}"
        distribute_states(inst, list(pool))
        from mame_client import BridgeSession
        from mame_gym import SS2RoundEnv
        sess = BridgeSession(mode="1p", instance=inst)
        env = ResilientEnv(sess=sess, speed=speed,
                           repeat_penalty=repeat_penalty,
                           whiff_penalty=whiff_penalty,
                           allow_spam=getattr(args, 'allow_spam', False),
                           diversity_bonus=diversity_bonus, pool=pool,
                           cpu_governor=cpu_governor,
                           entity_obs=entity_obs,
                           intent_mode=intent_mode,
                           match_episodes=match_episodes,
                           n_intents=n_intents, stun_lock=stun_lock,
                           y_obs=y_obs,
                           hitbox_obs=hitbox_obs,
                           shape_events=shape_events,
                           time_penalty=time_penalty)
        env._ep = rank              # desync pool rotation across envs

        return env
    return _init


class EmaTracker:
    """kof97-recipe EMA shadow weights (TECHNIQUES.md §9: the single best
    stability trick). Updated once per rollout by EmaCallback; saved beside
    every checkpoint as ema_<steps>.zip for offline diag / Net2Net seeding.

    Works on SB3 param dicts: floats get exponential blending, non-floats
    (buffers) are copied verbatim."""

    def __init__(self, model, decay: float = 0.99):
        self.decay = decay
        self.shadow = {k: v.clone() for k, v in
                       model.get_parameters()["policy"].items()}

    def update(self, model) -> None:
        params = model.get_parameters()["policy"]
        for k, sh in self.shadow.items():
            v = params[k]
            if v.dtype.is_floating_point:
                sh.mul_(self.decay).add_(v, alpha=1 - self.decay)
            else:
                sh.copy_(v)

    def apply(self, model) -> None:
        """Swap the EMA weights in (COPY into the live tensors — never
        reassign storage, or the optimizer's references would write into
        the shadow), remembering the live ones for restore()."""
        import torch
        params = model.get_parameters()["policy"]
        self._backup = {k: v.clone() for k, v in params.items()}
        with torch.no_grad():
            for k, sh in self.shadow.items():
                params[k].copy_(sh)

    def restore(self, model) -> None:
        import torch
        params = model.get_parameters()["policy"]
        with torch.no_grad():
            for k, v in self._backup.items():
                params[k].copy_(v)


class EmaCallback(BaseCallback):
    """Update the shadow weights once per rollout."""

    def __init__(self, tracker: EmaTracker):
        super().__init__()
        self.tracker = tracker

    def _on_step(self) -> bool:
        return True

    def _on_rollout_end(self) -> None:
        self.tracker.update(self.model)


class ResilientEnv(SS2RoundEnv):
    """SS2RoundEnv with one-shot bridge rebuild on transient failures.
    A real gymnasium.Env subclass, so SB3's env checks accept it."""

    def reset(self, **kw):
        try:
            return super().reset(**kw)
        except Exception:
            self.sess._rebuild()
            return super().reset(**kw)

    def step(self, action):
        try:
            return super().step(action)
        except Exception:
            self.sess._rebuild()
            obs, info = super().reset()
            # error-neutral step back to SB3
            return obs, 0.0, False, False, info


def free_ram_gb() -> float:
    import ctypes

    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    st = MS()
    st.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return st.ullAvailPhys / 2 ** 30


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", type=int, nargs="?", default=150_000)
    ap.add_argument("--model", default=None, help="init from this ckpt (zip)")
    ap.add_argument("--pool", default="lad1,lad2",
                    help="comma list of pool states, e.g. lad8,lad8,lad7")
    ap.add_argument("--repeat-penalty", type=float, default=0.05)
    ap.add_argument("--repeat-penalty-start", type=float, default=0.005)
    ap.add_argument("--whiff-penalty", type=float, default=0.02)
    ap.add_argument("--whiff-penalty-start", type=float, default=0.0)
    ap.add_argument("--diversity-bonus", type=float, default=0.0,
                    help="beautiful-play shaping: 0 = off (pass-first)")
    ap.add_argument("--speed", type=int, default=2,
                    help="emulation speed multiplier (2 = CPU-safe)")
    ap.add_argument("--device", default="cuda",
                    help="PPO device: cuda (GPU updates, frees CPU) or cpu")
    ap.add_argument("--no-governor", action="store_true",
                    help="disable the runtime CPU governor")
    ap.add_argument("--n-envs", type=int, default=0,
                    help="parallel instances (0 = auto by free RAM, max 6)")
    ap.add_argument("--entity-obs", action="store_true",
                    help="T11 25-dim entity observation (dx dual-channel + "
                         "state flag matrix); REQUIRED for new-gen policies, "
                         "incompatible with all pre-T11 checkpoints")
    ap.add_argument("--action-mode", choices=["direct", "intent"],
                    default="direct",
                    help="intent = C2 reflex layer (Discrete(8) tactical "
                         "intents translated/overridden by range-gated "
                         "reflexes; requires --entity-obs)")
    ap.add_argument("--match-episodes", action="store_true",
                    help="T18: the training episode is a COMPLETE best-of-3 "
                         "match (round KOs score, 2 round wins/losses end "
                         "it) — pairs with --entity-obs")
    ap.add_argument("--n-intents", type=int, default=8,
                    help="R2: intent-space size (9 = +jump; 8 keeps V1/V2 "
                         "checkpoints loadable)")
    ap.add_argument("--stun-lock", action="store_true",
                    help="R2: own-hitstun forces idle (SFAgents animation-"
                         "lock lesson; opt-in keeps legacy eval semantics)")
    ap.add_argument("--hitbox-obs", action="store_true",
                    help="R2: append 5-dim Hitbox features -> obs 64d "
                         "(REQUIRES --y-obs; enforced)")
    ap.add_argument("--y-obs", action="store_true",
                    help="R2: append Y-height channels (uid+0x50, /256) -> "
                         "obs 54d; required for transplanted 54d models")
    ap.add_argument("--shape-events", action="store_true",
                    help="R3: latch-event shaping (counter-hit +0.3 / "
                         "anti-air +0.2, overlap pays the single higher)")
    ap.add_argument("--time-penalty", type=float, default=0.0,
                    help="R3: reward per DECISION step (calibrate from "
                         "diag steps p90 BEFORE a long run; plan §二C3)")
    ap.add_argument("--allow-spam", action="store_true",
                    help="MoE bypass: allow continuous attack spam, bypass anti_spam")
    ap.add_argument("--instance-prefix", default="rl",
                    help="MAME instance dir prefix (BUG-15 co-existence: "
                         "use a unique prefix per concurrent run)")
    ap.add_argument("--no-ema", action="store_true",
                    help="disable the kof97-recipe EMA shadow weights "
                         "(updated per rollout, saved as ema_<steps>.zip)")
    args = ap.parse_args(argv)
    if args.hitbox_obs and not args.y_obs:
        ap.error("--hitbox-obs requires --y-obs (hitbox channels are "
                 "defined on the 54d R2 base; review P0-1)")
    steps = args.steps
    pool = [s.strip() for s in args.pool.split(",") if s.strip()]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT / "data" / "rl" / f"ppo_smoke_{stamp}"
    tb_dir = PROJECT / "logs" / "rl_tb" / stamp
    progress = PROJECT / "logs" / f"rl_train_{stamp}.jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)
    tb_dir.mkdir(parents=True, exist_ok=True)

    # Hard rule: background-friendly priority (BelowNormal 0x4000) and track PID
    try:
        import ctypes
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.kernel32.SetPriorityClass(handle, 0x00004000)
    except Exception:
        pass
    try:
        (PROJECT / "logs").mkdir(parents=True, exist_ok=True)
        (PROJECT / "logs" / "rl_train_last.txt").write_text(f"{_os.getpid()}|{stamp}\n", encoding="ascii")
    except Exception:
        pass

    pass  # torch imported at module top (shm.dll ordering fix)
    torch.set_num_threads(4)      # bound PPO update bursts (default 16)
    from stable_baselines3 import PPO
    from stable_baselines3.common.evaluation import evaluate_policy
    from mame_gym import SS2RoundEnv

    env = SS2RoundEnv(speed=4, repeat_penalty=args.repeat_penalty_start,
                      whiff_penalty=args.whiff_penalty_start,
                      diversity_bonus=args.diversity_bonus, pool=pool)
    # kof97_rl recipe subset: small MLP, ENTROPY ANNEAL (0.01 -> 0.002 over
    # the run — the proven stability trick; a flat ent_coef keeps the argmax
    # mode spamming forever while the sampled policy looks healthy),
    # linear lr anneal (SB3 default); device=cpu (SB3: MlpPolicy trains
    # faster on CPU)
    n_envs = args.n_envs
    if n_envs == 0:
        n_envs = max(2, min(6, int((free_ram_gb() - 2.0) / 0.45)))
    # CPU budget (user mandate: total CPU <= 70%): ~2.5 logical cores per
    # instance (MAME 4x + trainer). Abort/reduce when the machine is busy.
    import ctypes as _ct

    class _MS(_ct.Structure):
        _fields_ = [("dwLength", _ct.c_ulong), ("dwMemoryLoad", _ct.c_ulong),
                    ("_pad", _ct.c_ulonglong * 6)]

    def cpu_load_pct() -> int:
        st = _MS()
        st.dwLength = _ct.sizeof(_MS)
        k32 = _ct.windll.kernel32
        # GlobalMemoryStatusEx is not CPU; use WMI-free fallback via pdh? Use
        # psutil-free approach: GetSystemTimes (idle/kernel/user)
        idle1, kern1, user1 = (_ct.c_ulonglong(), _ct.c_ulonglong(),
                               _ct.c_ulonglong())
        k32.GetSystemTimes(_ct.byref(idle1), _ct.byref(kern1),
                           _ct.byref(user1))
        _ct.windll.kernel32.Sleep(500)
        idle2, kern2, user2 = (_ct.c_ulonglong(), _ct.c_ulonglong(),
                               _ct.c_ulonglong())
        k32.GetSystemTimes(_ct.byref(idle2), _ct.byref(kern2),
                           _ct.byref(user2))
        d_idle = idle2.value - idle1.value
        d_total = ((kern2.value - kern1.value)
                   + (user2.value - user1.value))
        return int(100 * (1 - d_idle / max(d_total, 1)))

    load = cpu_load_pct()
    cap = {0: 4, 1: 2}.get(load // 35, 0) or (4 if load < 35 else 2)
    if load >= 70:
        print(f"[train] CPU {load}% >= 70% - machine busy, aborting. "
              f"Run later.", flush=True)
        sys.exit(2)
    if n_envs > cap:
        print(f"[train] CPU {load}%: reducing n_envs {n_envs} -> {cap}",
              flush=True)
        n_envs = cap
    print(f"[train] n_envs={n_envs} (free RAM {free_ram_gb():.1f}GB, "
          f"CPU {load}%)", flush=True)
    if n_envs > 1:
        from stable_baselines3.common.vec_env import SubprocVecEnv, VecMonitor
        fns = [make_env(i, pool, args.repeat_penalty, args.whiff_penalty_start,
                        args.diversity_bonus, args.speed,
                        not args.no_governor, args.entity_obs,
                        args.action_mode == "intent",
                        n_intents=args.n_intents, stun_lock=args.stun_lock,
                        y_obs=args.y_obs,
                        hitbox_obs=args.hitbox_obs,
                        shape_events=args.shape_events,
                        time_penalty=args.time_penalty,
                        instance_prefix=args.instance_prefix)
               for i in range(n_envs)]
        venv = VecMonitor(SubprocVecEnv(fns))
        train_env = venv
        eval_inst = f"{args.instance_prefix}e"
        distribute_states(eval_inst, list(pool))
        from mame_client import BridgeSession
        from mame_gym import SS2RoundEnv as _SRE
        eval_sess = BridgeSession(mode="1p", instance=eval_inst)
        env = ResilientEnv(sess=eval_sess, speed=4,
                           repeat_penalty=args.repeat_penalty,
                           whiff_penalty=args.whiff_penalty_start,
                           diversity_bonus=args.diversity_bonus, pool=pool,
                           allow_spam=args.allow_spam,
                           entity_obs=args.entity_obs,
                           intent_mode=args.action_mode == "intent",
                           match_episodes=args.match_episodes,
                           n_intents=args.n_intents,
                           stun_lock=args.stun_lock,
                           y_obs=args.y_obs,
                           hitbox_obs=args.hitbox_obs,
                           shape_events=args.shape_events,
                           time_penalty=args.time_penalty)
    else:
        env = SS2RoundEnv(speed=args.speed,
                          repeat_penalty=args.repeat_penalty_start,
                          whiff_penalty=args.whiff_penalty_start,
                          diversity_bonus=args.diversity_bonus, pool=pool,
                          entity_obs=args.entity_obs,
                          intent_mode=args.action_mode == "intent",
                          match_episodes=args.match_episodes,
                          n_intents=args.n_intents,
                          stun_lock=args.stun_lock,
                          y_obs=args.y_obs,
                          hitbox_obs=args.hitbox_obs,
                          shape_events=args.shape_events,
                          time_penalty=args.time_penalty)
        train_env = env
    if args.model:
        print(f"[train] init from {args.model} (device={args.device})",
              flush=True)
        model = PPO.load(args.model, env=train_env, device=args.device,
                         tensorboard_log=str(tb_dir))
    else:
        model = PPO("MlpPolicy", train_env, n_steps=256, batch_size=256,
                    n_epochs=10,
                    learning_rate=2.5e-4, ent_coef=0.01, gamma=0.995,
                    gae_lambda=0.95, policy_kwargs=dict(net_arch=[64, 64]),
                    device=args.device, seed=0, verbose=0,
                    tensorboard_log=str(tb_dir))

    # kof97 stability trick: EMA shadow weights, updated once per rollout,
    # saved beside every checkpoint as ema_<steps>.zip (offline diag /
    # Net2Net seeding). Selection stays on the live model's stochastic score.
    ema = None if args.no_ema else EmaTracker(model)
    ema_cb = (EmaCallback(ema) if ema else None)

    def log(event: dict) -> None:
        event["t"] = round(time.time() - t0, 1)
        with progress.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        print(json.dumps(event, ensure_ascii=False), flush=True)

    t0 = time.time()
    log({"ev": "start", "steps": steps, "out": str(out_dir), "pool": pool,
         "repeat_penalty": args.repeat_penalty,
         "whiff_penalty": args.whiff_penalty, "model": args.model,
         "n_envs": n_envs, "instance_prefix": args.instance_prefix,
         "shape_events": args.shape_events,
         "time_penalty": args.time_penalty,
         "hitbox_obs": args.hitbox_obs, "y_obs": args.y_obs})

    from stable_baselines3.common.callbacks import BaseCallback

    class EvalKeepalive(BaseCallback):
        """Ping the idle eval-instance bridge every rollout: the MAME Lua
        bridge self-exits after 120s without commands."""

        def _on_step(self) -> bool:
            return True

        def _on_rollout_start(self) -> None:
            try:
                eval_sess.call("ping", timeout=5.0)
            except Exception:
                pass

    keepalive = EvalKeepalive()

    ckpt_every = 25_000
    done = 0
    best = -1e9
    best_det = -1e9
    while done < steps:
        chunk = min(ckpt_every, steps - done)
        # entropy anneal across the whole run (0.01 -> 0.002)
        frac = done / max(steps, 1)
        model.ent_coef = 0.01 - 0.008 * frac
        # penalty anneal: the 7/8 winner must ADAPT to the anti-cheese
        # pressure gradually (a hard 0.05 cliff produced det=-170 spam-lock)
        ramped = args.repeat_penalty_start + (args.repeat_penalty
                                              - args.repeat_penalty_start) * frac
        env.repeat_penalty = ramped
        try:
            for e in getattr(train_env, "envs", []):
                e.repeat_penalty = ramped
        except Exception:
            pass
        # whiff-penalty anneal (2026-11-11): the precise T5 latch signal
        # raised the EFFECTIVE whiff pressure (hidden zoom whiffs now counted)
        # and the 300k run collapsed det to walkL — ramp it like the repeat
        # penalty so the policy adapts gradually
        wramped = args.whiff_penalty_start + (args.whiff_penalty
                                              - args.whiff_penalty_start) * frac
        env.whiff_penalty = wramped
        try:
            for e in getattr(train_env, "envs", []):
                e.whiff_penalty = wramped
        except Exception:
            pass
        cbs = [keepalive] + ([ema_cb] if ema_cb else [])
        model.learn(total_timesteps=chunk, reset_num_timesteps=False,
                    tb_log_name="ppo", callback=cbs)
        done += chunk
        # audit 3.3: a match-episode eval runs 2-3 FULL matches — halve the
        # episode count there or the 20 evals over 500k stall the run
        n_eval = 2 if args.match_episodes else 3
        mean_r, std_r = evaluate_policy(model, env, n_eval_episodes=n_eval,
                                        warn=False)
        stoch_r, stoch_std = evaluate_policy(model, env, n_eval_episodes=n_eval,
                                             warn=False, deterministic=False)
        model.save(str(out_dir / f"ppo_{done}"))
        if ema is not None:
            ema.update(model)          # close the chunk's last rollout gap
            ema.apply(model)
            model.save(str(out_dir / f"ema_{done}"))
            ema.restore(model)
        # best-ckpt selection on the STOCHASTIC score: PPO improves the
        # sampled policy (2026-11-08 evidence: argmax trajectory can stay
        # frozen for 200k steps while the sampled one climbs); the entropy
        # anneal then freezes that quality into near-deterministic play
        score = stoch_r
        if score > best:
            best = score
            model.save(str(out_dir / "best"))
            log({"ev": "best", "steps": done, "stoch_mean": round(stoch_r, 3),
                 "det_mean": round(mean_r, 3)})
        # R2 (review P1-2): dual-track best. best.zip stays STOCH-selected
        # (project convention + watch_agent registry), best_det.zip tracks
        # the deterministic score — both PROVISIONAL (n=2 eval episodes);
        # the final best per track comes from the post-training fixed eval.
        if mean_r > best_det:
            best_det = mean_r
            model.save(str(out_dir / "best_det"))
            log({"ev": "best_det", "steps": done,
                 "det_mean": round(mean_r, 3)})
        # whiff-rate probe (T5 acceptance metric): 1 stoch episode, aggregate
        # the env's whiff/attack counters — makes the -50% gate trackable
        # per checkpoint without a separate diag run
        wh = at = tp = evc = eva = thr = 0
        try:
            obs, _ = env.reset()
            done_w = False
            while not done_w:
                a, _ = model.predict(obs, deterministic=False)
                obs, _r, term, trunc, info = env.step(int(a))
                done_w = term or trunc
                wh = info.get("whiffs", wh)
                at = info.get("attacks", at)
                tp = info.get("time_paid", 0)
                evc = info.get("ev_ch", 0)
                eva = info.get("ev_aa", 0)
                thr = info.get("threat_obs", 0)
        except Exception:  # noqa: BLE001
            pass
        wr = round(wh / at, 3) if at else -1.0
        log({"ev": "ckpt", "steps": done, "eval_mean": round(mean_r, 3),
             "eval_std": round(std_r, 3), "stoch_mean": round(stoch_r, 3),
             "whiff_rate": wr, "whiffs": wh, "attacks": at,
             "ent_coef": round(model.ent_coef, 4),
             "time_paid": round(tp, 4), "ev_counter": evc,
             "ev_anti_air": eva, "threat_obs": thr})

    model.save(str(out_dir / "final"))
    log({"ev": "done", "wall_s": round(time.time() - t0, 1), "best": round(best, 3)})
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))