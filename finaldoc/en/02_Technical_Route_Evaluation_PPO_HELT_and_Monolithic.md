# 02. Technical Route Evaluation: PPO, HELT League, Monolithic Nets vs. MoE

> **Location**: `finaldoc/en/02_Technical_Route_Evaluation_PPO_HELT_and_Monolithic.md`  
> **Chinese Counterpart**: [../02_技术路线评估与深度剖析_PPO_HELT联赛与大一统网络.md](../02_技术路线评估与深度剖析_PPO_HELT联赛与大一统网络.md)  
> **Evaluation Note**: Comparisons below are qualitative engineering assessments grounded in this project's single-machine Windows MAME experience.

---

## 1. Multi-Dimensional Route Comparison

| Dimension | Scratch Monolithic PPO | Self-Play League (HELT*) | End-to-End Monolithic Net | Decoupled MoE (This Project) |
| :--- | :--- | :--- | :--- | :--- |
| **Single-PC Compute** | Medium (slow on single-core MAME) | Very High (requires multi-node/multi-core pool) | High (GPU memory + large batches) | **Very Low** (fast single-PC search/eval) |
| **Iteration Speed** | Slow (hours to days per experiment) | Very Slow (weeks on cluster) | Slow (prone to oscillation) | **Fast** (minutes to hours per matchup) |
| **Cross-Opponent Interference** | Severe (gradient conflict) | Managed via large league pool | Severe (catastrophic forgetting) | **Zero** (physically isolated per-opponent JSONs) |
| **Interpretability & Debugging** | Low (black-box weights) | Low | Low | **High** (explicit intent sequences & distance thresholds) |
| **Generalization vs. Humans** | Moderate (once converged) | **Best** (approaches Nash equilibrium) | Fragile without massive data | Requires closed-loop reactive or BC+PPO upgrade |
| **Single-PC Delivery Reliability** | Low (prone to turtle local optimum) | Very Low on single PC | Low | **Verified 16/16 Bo3 Clear** |

*\*HELT (Historical Evaluation and League Training) is this project's internal term for AlphaStar-style self-play league training.*

---

## 2. Route 1: When Should PPO Be Re-Introduced?

Pure from-scratch PPO struggled because of sparse round-end rewards, reward-shaping turtle traps, and single-PC MAME throughput limits.

**Recommended Future Path — Imitation Cold-Start + Residual PPO**:
1. Replay the 16 verified MoE experts inside `SS2RoundEnv` to collect full entity-observation demonstration trajectories `(obs, act, r, next_obs, done)`.
2. Pretrain an SB3-compatible policy via **Behavior Cloning (BC)** so the agent starts already capable of blocking, approaching, and whiff-punishing.
3. Warm up the Critic first, then apply low-learning-rate **PPO / Residual RL** fine-tuning to gain robustness against perturbed openings and human opponents (see [10_MoE_to_PPO_and_Advanced_RL_Roadmap.md](./10_MoE_to_PPO_and_Advanced_RL_Roadmap.md)).

---

## 3. Route 2: Feasibility of Self-Play League Training (HELT)

1. **Compute Bottleneck**: Maintaining even a minimal league (1 main agent + 2 exploiters + 4 historical snapshots) requires 6–8 concurrent MAME processes, saturating a consumer PC's CPU and memory.
2. **Non-Transitive Cycling ("Spinning Top")**: Fighting games are rock-paper-scissors (`fast pokes > jump-in > crouch-guard > fast pokes`). Small-scale self-play frequently cycles without raising absolute skill.
3. **Objective Mismatch for Arcade Clear**: Arcade CPUs run fixed state machines with deterministic punish windows; self-play mind-games optimized against other AIs often lose to blunt arcade CPU patterns.

**Conclusion**: Avoid full-scale HELT on a single PC; instead, reuse the 16 MoE experts as **frozen sparring anchors** inside future PPO training.

---

## 4. Route 3: Monolithic Network vs. MoE (and Hierarchical MoE)

- **Monolithic Pitfalls**: Negative transfer across matchups (jumping beats Galford's dog but gets anti-aired by Kyoshiro), expensive full-roster regression tests after every tweak, and rugged loss landscapes.
- **MoE Advantage**: Static opponent-ID routing (`MoEAgent.set_opponent`) isolates every matchup in its own `vs_<char>.json` file—fixing Hanzo or Mizuki cannot regress Genjuro or Earthquake.
- **Next-Gen Architecture — Hierarchical MoE**: Combine a **shared fighting-game representation backbone** (learning universal spacing, hitbox reach, and frame advantage) with **decoupled per-opponent expert heads** selected by a router.
