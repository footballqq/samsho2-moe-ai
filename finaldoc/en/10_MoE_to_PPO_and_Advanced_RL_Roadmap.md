# 10. MoE-to-PPO & Advanced RL Training Roadmap

> **Location**: `finaldoc/en/10_MoE_to_PPO_and_Advanced_RL_Roadmap.md`  
> **Chinese Counterpart**: [../10_MoE资产反哺PPO与强化学习进阶训练路线指南.md](../10_MoE资产反哺PPO与强化学习进阶训练路线指南.md)  
> **Scope**: Architecture and experimental roadmap (design specification only; no unverified win-rate claims).

---

## 1. Motivation: Bridging MoE Specialists and Generalizable Neural RL

Training PPO from scratch on **Samurai Shodown II** hits three well-known failure modes:
1. **Cold-Start Avoidance Local Optimum**: Random policies approaching high-level arcade CPUs take heavy punishment and collapse into passive back-walking/turtling before discovering guard-to-punish payoffs.
2. **Long-Horizon Sparse Credit Assignment**: Reaching KO spans hundreds of decision steps, making terminal rewards noisy.
3. **Emulator Throughput Ceiling**: Single-machine MAME rollouts constrain pure online trial-and-error.

Conversely, the delivered **16/16 MoE expert library** (`models/experts/vs_*.json`) reliably produces high-reward winning trajectories against every opponent, while lacking full generalization against randomized states or adaptive human players. Using these MoE experts as **teachers, trajectory generators, and frozen sparring anchors** directly unlocks neural RL training.

---

## 2. Asset Readiness & Data Boundary

| Asset | Location | Status | Role in RL Training |
| :--- | :--- | :--- | :--- |
| **16 Verified MoE Experts** | `models/experts/vs_*.json` | Ready | Deterministic & distance-reactive teacher policies |
| **17 Savestate Anchors** | `data/mame/instance/rl/state/samsho2/*.sta` | Ready | Instant round-1 resets with zero menu overhead |
| **WRAM Gym Environment** | `src/mame_gym.py` | Ready | Produces full entity observation vectors (`obs`) + 9-intent actions |
| **Text Demo Logs** | `logs/demos/*.log` | HP + action only | Audit logs only; **not** sufficient as state inputs for BC/Offline RL |
| **Full Trajectory Dataset** | *(Replay to collect)* | Needs 5-min replay | Replay the 16 experts inside `SS2RoundEnv` to record full `(obs, act, r, next_obs, done, char_id)` |

---

## 3. Five Core Training Pathways

### Pathway 1: Behavior Cloning (BC) Pretraining + PPO Fine-Tuning *(Recommended MVP)*
- Replay the 16 MoE experts inside `SS2RoundEnv` (with mild opening/state perturbations to broaden state coverage) to collect a compact `(obs, act)` demonstration dataset.
- Pretrain an SB3-compatible `MlpPolicy` via class-balanced cross-entropy (`ppo_bc_init.zip`) so PPO starts from a competent, combat-ready policy rather than random avoidance.
- **Critical Guardrail — Critic Warmup**: Because BC trains only the Actor, freeze the policy head (`pi`) for the initial PPO steps while training only the value head (`vf`); unfreeze the full network with a low learning rate once value predictions stabilize.

### Pathway 2: Kickstarting (Policy Distillation into PPO)
- Add a decaying KL-divergence term toward the MoE teacher inside the PPO objective:
  $$L_{\text{total}} = L_{\text{PPO}} + \lambda(t) \cdot D_{\text{KL}}\!\left(\pi_{\text{MoE}}(\cdot \mid s) \,\|\, \pi_{\text{PPO}}(\cdot \mid s)\right)$$
- Anneal $\lambda(t) \to 0$ over training so PPO retains early defensive/punish habits while eventually surpassing the teacher on unseen states.

### Pathway 3: Go-Explore / Backplay Endgame Curriculum
- Let MoE experts advance to late-round states (low HP, corner pressure, wakeup) and save intermediate `.sta` snapshots.
- Train PPO first from "two hits from KO" endgames to master finishing, then step the start state backward toward round start.

### Pathway 4: Offline RL (IQL / CQL / Decision Transformer)
- Combine **MoE winning trajectories** (high-return positive data) with **historical PPO exploratory/losing trajectories** (medium/low-return data) into a mixed `(s, a, r, s', done)` dataset.
- Train **IQL** or **CQL** entirely on GPU—bypassing MAME's online FPS ceiling—to stitch strong closed-loop behaviors before live MAME evaluation.

### Pathway 5: Frozen Anchors in Self-Play / League Training
- In True 2P VS mode, deploy the 16 MoE experts (especially closed-loop `DistanceReactivePolicy` configs) as **frozen sparring partners** alongside self-play to prevent cyclic forgetting and provide a fixed regression benchmark.

---

## 4. Recommended 3-Stage MVP Validation Plan

1. **Stage 1 (Trajectory Collection)**: Replay all 16 experts in `SS2RoundEnv` with light perturbation and save `.npz` (`obs`, `actions`, `rewards`, `dones`, `char_ids`) matching `train_rl.py`'s exact observation switches.
2. **Stage 2 (BC Initialization)**: Train `ppo_bc_init.zip` and verify zero-shot live MAME evaluation confirms elimination of passive avoidance.
3. **Stage 3 (PPO Fine-Tuning & 3-Gate Audit)**: Run Critic warmup + low-LR PPO fine-tuning, then evaluate across (a) standard 16-opponent anchors, (b) perturbed openings, and (c) live Human 2P VS matches via `.\play_demo.ps1 -Human`.
