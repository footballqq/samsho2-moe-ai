"""
mame_moe.py - Mixture of Experts (MoE) Architecture for Samurai Shodown II.
Encapsulates specialized single-character policies (neural PPO or deterministic sequences)
behind a unified SB3-compatible interface.
"""
import json
from pathlib import Path
from typing import Dict, Tuple, Optional, Any, Union, List
import numpy as np
from stable_baselines3 import PPO
from mame_hitbox import normalize_char_name


class SequencePolicy:
    """Deterministic sequence/exploit policy compatible with SB3 predict interface.
    Supports fixed action sequences as well as prefix + loop combo patterns.
    """

    def __init__(self, actions: Union[List[int], Dict[str, Any]]):
        if isinstance(actions, dict):
            self.prefix = list(actions.get("prefix", []))
            self.loop = list(actions.get("loop", actions.get("actions", [])))
        else:
            self.prefix = []
            self.loop = list(actions)
        self.idx = 0

    def reset(self):
        self.idx = 0

    def predict(
        self,
        observation: np.ndarray,
        state: Optional[Tuple[np.ndarray, ...]] = None,
        episode_start: Optional[np.ndarray] = None,
        deterministic: bool = True,
    ) -> Tuple[int, Optional[Tuple[np.ndarray, ...]]]:
        if episode_start is not None and np.any(episode_start):
            self.reset()
        if self.idx < len(self.prefix):
            act = self.prefix[self.idx]
        elif self.loop:
            act = self.loop[(self.idx - len(self.prefix)) % len(self.loop)]
        else:
            act = 0
        self.idx += 1
        return act, state


class DistanceReactivePolicy:
    """Closed-loop distance-aware policy using entity_obs dist channel (feat[1]).

    When dist > far_thresh, executes far_loop (approach / jump-in);
    once inside combat range, executes close_loop (slash / guard / punish).
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.prefix = list(cfg.get("prefix", []))
        self.far_thresh = float(cfg.get("far_thresh", 0.28))
        self.far_loop = list(cfg.get("far_loop", [0, 0, 7]))
        self.close_loop = list(cfg.get("close_loop", [3, 3, 7]))
        self.idx = 0
        self.far_idx = 0
        self.close_idx = 0

    def reset(self):
        self.idx = 0
        self.far_idx = 0
        self.close_idx = 0

    def predict(
        self,
        observation: np.ndarray,
        state: Optional[Tuple[np.ndarray, ...]] = None,
        episode_start: Optional[np.ndarray] = None,
        deterministic: bool = True,
    ) -> Tuple[int, Optional[Tuple[np.ndarray, ...]]]:
        if episode_start is not None and np.any(episode_start):
            self.reset()
        if self.idx < len(self.prefix):
            act = self.prefix[self.idx]
            self.idx += 1
            return act, state

        # Latest stacked frame starts at len(obs) // 2; index 1 is normalized |dx|/512
        dist = 0.0
        if observation is not None and len(observation) >= 4:
            half = len(observation) // 2
            dist = float(observation[half + 1])

        if dist > self.far_thresh and self.far_loop:
            act = self.far_loop[self.far_idx % len(self.far_loop)]
            self.far_idx += 1
        elif self.close_loop:
            act = self.close_loop[self.close_idx % len(self.close_loop)]
            self.close_idx += 1
        else:
            act = 0
        self.idx += 1
        return act, state


class PerRoundPolicy:
    """Multi-round specialist router decoupling Round 1, Round 2, and Round 3 strategies."""

    def __init__(self, round_configs: Dict[str, Any]):
        self.round_policies: Dict[int, Any] = {}
        for r in [1, 2, 3]:
            key = f"round_{r}"
            if key in round_configs:
                cfg = round_configs[key]
                if isinstance(cfg, dict) and cfg.get("type") == "reactive":
                    self.round_policies[r] = DistanceReactivePolicy(cfg)
                else:
                    self.round_policies[r] = SequencePolicy(cfg)
        default_seq = round_configs.get("winning_trace", round_configs.get("loop", [8, 8, 6, 3, 7]))
        self.default_policy = SequencePolicy(default_seq)
        self.current_round = 1
        self.active_policy = self.round_policies.get(1, self.default_policy)

    def set_round(self, round_no: int):
        self.current_round = round_no
        self.active_policy = self.round_policies.get(round_no, self.default_policy)
        if hasattr(self.active_policy, "reset"):
            self.active_policy.reset()

    def reset(self):
        if hasattr(self.active_policy, "reset"):
            self.active_policy.reset()

    def predict(
        self,
        observation: np.ndarray,
        state: Optional[Tuple[np.ndarray, ...]] = None,
        episode_start: Optional[np.ndarray] = None,
        deterministic: bool = True,
    ) -> Tuple[int, Optional[Tuple[np.ndarray, ...]]]:
        return self.active_policy.predict(
            observation, state=state, episode_start=episode_start, deterministic=deterministic
        )


class MoEAgent:
    """Unified Agent wrapper routing inferences to character-specific experts."""

    def __init__(
        self,
        experts_dir: Union[str, Path],
        default_model_path: Optional[Union[str, Path]] = None,
        device: str = "auto",
        lazy_load: bool = True
    ):
        self.experts_dir = Path(experts_dir)
        self.default_model_path = Path(default_model_path) if default_model_path else None
        self.device = device
        self.lazy_load = lazy_load
        
        # Expert cache: {canonical_char_name: PPO_or_SequencePolicy}
        self.experts: Dict[str, Any] = {}
        self.current_char: str = "haowmaru"
        self._active_policy: Optional[Any] = None

        if not lazy_load:
            self._preload_all()

    def _resolve_model_path(self, char_name: str) -> Optional[Path]:
        canon = normalize_char_name(char_name)
        # 1. Look for deterministic sequence expert .json first
        json_candidate = self.experts_dir / f"vs_{canon}.json"
        if json_candidate.exists():
            return json_candidate
        # 2. Look for vs_<canon>.zip in experts_dir
        zip_candidate = self.experts_dir / f"vs_{canon}.zip"
        if zip_candidate.exists():
            return zip_candidate
        # 3. Fallback to default
        if self.default_model_path and self.default_model_path.exists():
            return self.default_model_path
        return None

    def _load_expert(self, char_name: str) -> Any:
        canon = normalize_char_name(char_name)
        if canon in self.experts:
            return self.experts[canon]

        path = self._resolve_model_path(canon)
        if path is None:
            raise FileNotFoundError(
                f"[MoE] No expert model found for '{canon}' and no default model provided."
            )

        print(f"[MoE] Loading expert policy for '{canon}' from {path.name}...")
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            if "round_1" in data or "round_2" in data or "round_3" in data:
                policy = PerRoundPolicy(data)
            else:
                trace = data.get("winning_trace", data.get("actions", data.get("loop", [])))
                policy = SequencePolicy(trace)
        else:
            policy = PPO.load(path, device=self.device)
            
        self.experts[canon] = policy
        return policy

    def _preload_all(self):
        """Preload all available expert checkpoints in experts_dir."""
        for p in self.experts_dir.glob("vs_*.json"):
            char_key = p.stem.replace("vs_", "")
            self.experts[char_key] = self._load_expert(char_key)
        for p in self.experts_dir.glob("vs_*.zip"):
            char_key = p.stem.replace("vs_", "")
            if char_key not in self.experts:
                self.experts[char_key] = PPO.load(p, device=self.device)
        print(f"[MoE] Preloaded {len(self.experts)} expert policies.")

    def set_opponent(self, opponent_identity: Union[str, int, None]):
        """Select active policy based on opponent identity (int ID or state name)."""
        self.current_char = normalize_char_name(opponent_identity)
        self._active_policy = self._load_expert(self.current_char)
        if hasattr(self._active_policy, "reset"):
            self._active_policy.reset()

    def reset(self):
        """Reset the active expert policy (e.g. sequence pointer)."""
        if self._active_policy is not None and hasattr(self._active_policy, "reset"):
            self._active_policy.reset()

    def set_round(self, round_no: int):
        """Notify the active expert of the current round number (1, 2, 3)."""
        if self._active_policy is not None and hasattr(self._active_policy, "set_round"):
            self._active_policy.set_round(round_no)

    def predict(
        self,
        observation: np.ndarray,
        state: Optional[Tuple[np.ndarray, ...]] = None,
        episode_start: Optional[np.ndarray] = None,
        deterministic: bool = True,
    ) -> Tuple[Any, Optional[Tuple[np.ndarray, ...]]]:
        """Transparent SB3 predict interface; delegates forward pass to active expert."""
        if self._active_policy is None:
            self.set_opponent(self.current_char)
        act, st = self._active_policy.predict(
            observation,
            state=state,
            episode_start=episode_start,
            deterministic=deterministic
        )
        if isinstance(act, np.ndarray) and act.ndim == 0:
            act = int(act.item())
        return act, st
