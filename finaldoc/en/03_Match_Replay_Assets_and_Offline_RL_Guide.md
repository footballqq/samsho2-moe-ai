# 03. Match Replay Assets & Offline Learning Value Guide

> **Location**: `finaldoc/en/03_Match_Replay_Assets_and_Offline_RL_Guide.md`  
> **Chinese Counterpart**: [../03_对局录像资产与未来离线学习价值指南.md](../03_对局录像资产与未来离线学习价值指南.md)

---

## 1. Current Replay Assets & Honest Data-Density Breakdown

To keep research claims rigorous, we divide the repository's replay and logging assets into three explicit tiers:

| Tier | Asset | What It Contains Today | Suitable Use Cases |
| :--- | :--- | :--- | :--- |
| **Delivered (Ready)** | `models/experts/vs_*.json` + 17 `.sta` anchors | Executable winning policies & round-start snapshots | Deterministic replay & full-state trajectory generation |
| **Delivered (Ready)** | `logs/demos/*_VICTORY.log` (`DemoLogger`) | Step index, round number, intent ID/name, P1/P2 HP & ratio | Match auditing, win verification, motif inspection *(NOT sufficient alone as full RL state)* |
| **Delivered (Ready)** | `videos/*.mp4` + `_zh/_en.srt` + `_commentary.json` | 60 FPS video, bilingual subtitles, event timestamps | Presentations, video editing, VLM video-understanding benchmarks |
| **Replay-to-Collect** | Full `(obs, act, r, next_obs, done)` `.npz` | Full 25–64D WRAM entity observations + actions + rewards | **BC pretraining, Offline RL (IQL/CQL), Decision Transformer** |
| **Planned (Roadmap)** | MAME `.inp` input streams & DPO preference pairs | Lossless MAME input files; same-state `(chosen, rejected)` pairs | Future lossless playback & preference alignment |

### Actual `DemoLogger` Output Schema (`src/demo_logger.py`)
```text
Step 00001   | R1    | 7 (站立格挡 (GUARD))  | P1: 128/128 (100.0%) | P2: 128/164 (78.0%)
```
*(Note: `DemoLogger` writes HP and action intents, not full WRAM coordinates or fighter state flags. To train neural BC or Offline RL, replay the 16 MoE experts inside `SS2RoundEnv` and save the full `obs` tensor directly.)*

---

## 2. Four Offline Learning Applications (Once Full `obs` Trajectories Are Collected)

1. **Behavior Cloning (BC) Cold-Start**:
   $$\mathcal{L}_{\text{BC}}(\theta) = -\sum_{(s, a) \in \mathcal{D}} \log \pi_\theta(a \mid s)$$
   Replaying all 16 MoE experts (plus light state perturbation) gives a clean supervised dataset to initialize a PPO policy before online fine-tuning, skipping the passive-turtle cold-start phase.
2. **Offline RL (CQL / IQL / Decision Transformer)**:
   Mixing MoE winning trajectories (high return) with historical exploratory/losing PPO rollouts (low/medium return) enables pure-GPU offline value estimation and trajectory stitching without MAME's online FPS bottleneck.
3. **Preference Alignment (DPO — Research Hypothesis)**:
   Comparing clean 2–0 high-HP victories ($y_w$) against narrow low-HP scrapes ($y_l$) under matched states $x$ can shape decisive, low-risk fighting styles once same-state preference pairs are collected.
4. **Tactical Motif Mining**:
   Recurring intent sub-sequences such as `[GUARD -> ANTI_AIR -> SLASH]` or `[POKE -> POKE -> PUNISH]` can be extracted as interpretable playbooks or reflex guardrails.

---

## 3. Recommended Dataset Directory Convention

```text
data/datasets/
 ├── manifest.json                # Episode metadata (opponent, score, total steps, remaining HP)
 ├── npz/                         # Full-observation NumPy tensors for PyTorch / SB3
 │    ├── haohmaru_expert_train.npz
 │    └── haohmaru_expert_val.npz
 └── pairs/                       # Future DPO preference triplets
      └── dpo_preference_pairs.jsonl
```

For the concrete 3-stage MVP plan to turn these MoE experts into a pretrained PPO checkpoint, see [10_MoE_to_PPO_and_Advanced_RL_Roadmap.md](./10_MoE_to_PPO_and_Advanced_RL_Roadmap.md).
