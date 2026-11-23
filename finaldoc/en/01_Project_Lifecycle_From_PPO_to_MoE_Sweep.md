# 01. Project Lifecycle: From the PPO Impasse to a 16/16 MoE Clean Sweep

> **Location**: `finaldoc/en/01_Project_Lifecycle_From_PPO_to_MoE_Sweep.md`  
> **Chinese Counterpart**: [../01_项目全生命周期实录_从PPO困境到MoE全员通关.md](../01_项目全生命周期实录_从PPO困境到MoE全员通关.md)

---

## 1. Phase 1: Initial Exploration & The PPO Impasse

At the beginning of the project, we followed the classic Reinforcement Learning paradigm by training a single monolithic **PPO (Proximal Policy Optimization)** agent against a multi-opponent pool in MAME (`samsho2`). Three structural obstacles emerged:

1. **The Passive Turtle Trap (Local Optimum)**: Combining whiff penalties, repeat-action penalties, and damage-taken penalties created an unintended mathematical optimum where retreating to the corner and crouch-blocking yielded higher expected return than engaging—causing overnight PPO runs to collapse into passive time-out losses.
2. **Inter-Character Gradient Conflict**: The 16 Samurai Shodown II characters have radically opposing optimal counters (e.g., jump-in pressure vs. Earthquake's chain, strict defensive anti-air vs. Genjuro's Triple Slash, rushdown spacing vs. Mizuki's full-screen projectiles). Shared monolithic weights suffered severe catastrophic forgetting across matchups.
3. **Single-Machine Throughput & Cold-Start Sparsity**: Without demonstrations, random exploration rarely discovers a full `jump -> close -> heavy slash -> block` sequence, while single-core MAME simulation constrains online sample throughput.

---

## 2. Phase 2: Strategic Pivot to Mixture of Experts (MoE)

We pivoted from a single monolithic black-box policy to a decoupled **Mixture of Experts (MoE)** architecture built on two foundational abstractions:

### 2.1 9-Action Semantic Intent Space (SMDP)
Instead of raw frame-by-frame directional bits, policies output 9 human-readable combat intents (`src/moe_roster.py`):
- `0: APPROACH` | `1: RETREAT` | `2: POKE` | `3: SLASH` | `4: ANTI_AIR`
- `5: PUNISH` | `6: FIREBALL` | `7: GUARD` | `8: JUMP`

A low-level reflex/macro layer (`src/mame_macro.py`, `data/mame/movesets/haohmaru.yaml`) expands each intent into 2–8 frame physical inputs, forming a Semi-Markov Decision Process (SMDP).

### 2.2 Direct Neo-Geo WRAM Entity Perception
To eliminate pixel-bar zoom distortion, rage-flash misreads, and 15–30 frame HUD animation lag, we reverse-engineered Neo-Geo WRAM offsets directly (`src/mame_nav.py`, `src/mame_gym.py`):
- **P1 / P2 Entity UID Pointers**: `0x100A46` / `0x100A4A`
- **Authoritative Logical Health**: `UID + 0xBB` (1-byte unsigned integer; 128 standard, 164 Ukyo, 186 Sieger)
- **Hit Damage Latch**: `0x105ED3` (immediate hit confirmation)

---

## 3. Phase 3: The BUG-17 Postmortem & Six Hard Engineering Rules

During an overnight evaluation, automated metrics reported win rates jumping from 45% to 85%—yet live visual inspection revealed Haohmaru losing 0–2. A sign inversion in the timeout arbiter counted time-over losses as wins, and because the same arbiter powered training rewards, mid-eval, and final eval, all three layers mutually "confirmed" the bug.

This led to six permanent engineering rules (`AGENTS.md`):
1. **Cross-check arbiters against the game itself** (visible banners, KO text, human visual verification).
2. **Encode physical invariants in unit tests** (minimum round length, HP conservation, timer drainage).
3. **Derive verdict test expectations from real match traces**, not code reading.
4. **Monotonically improving metrics trigger component audits** (inspect win-by-KO vs. win-by-timeout share).
5. **Live visual spectator review is a hard release gate**.
6. **If a shared arbiter fails at one layer, invalidate and re-test all downstream layers**.

---

## 4. Phase 4: Best-of-3 (Bo3) State Machine & Per-Round Policies

Single-round victories do not represent full arcade matches. Between rounds, Samurai Shodown II executes ~60 frames of KO slow-motion, ~120 frames of victory banners, and ~100–200 frames of **asymmetric health refill** (loser refills to full; winner retains leftover HP).

We built `Bo3MatchController` (`src/bo3_controller.py`) with:
- Anti-flicker KO detection (`zs >= 3` consecutive zero-HP steps);
- Asymmetric `loser_refilled` detection before arming the next round;
- Mandatory `IDLE` lock during intermissions;
- `round_just_started` signaling to `PerRoundPolicy` (`src/mame_moe.py`), decoupling Round 1 opening bursts from Round 2/3 post-banner counter tactics—and supporting closed-loop `DistanceReactivePolicy` for fullscreen matchups (**Mizuki** and **Sieger**).

---

## 5. Phase 5: 16/16 Full-Roster Verification Milestone

Using systematic SMDP search, live Round 2 state sweeps, and closed-loop distance-reactive controllers, all 16 opponents were cleared in full Bo3 matches and recorded to 60 FPS MP4 with 18-second victory celebrations and bilingual subtitles:
- **Highlight Matchups**: Earthquake (2-1), Genjuro (2-0), Galford (2-0), Nakoruru (2-0), Cham Cham (2-1), Wan-Fu (2-1), Sieger (2-1, closed-loop reactive), Kyoshiro (2-0), Hanzo (2-1), Gen-An (2-0), Nicotine (2-0), Final Boss Mizuki (2-0, closed-loop reactive), Haohmaru Mirror (2-1), Ukyo (2-1), Jubei (2-1), and Charlotte (2-1).
- All 16 verified expert configs are stored in `models/experts/vs_<opponent>.json` and indexed in `models/experts/manifest.json`.
