# ⚔️ Samurai Shodown II: MoE Autonomous Fighter AI

**Language**: [中文 (Chinese)](README.md) | **English**

[![Platform](https://img.shields.io/badge/Platform-Neo--Geo%20%7C%20MAME-red.svg)](#)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](#)
[![Architecture](https://img.shields.io/badge/Architecture-SMDP%20%7C%20MoE-orange.svg)](#)
[![Status](https://img.shields.io/badge/Roster%20Cleared-16%2F16%20Verified%20(100%25)-brightgreen.svg)](#)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An autonomous fighting-game AI system for SNK's arcade classic **Samurai Shodown II (samsho2)** powered by **MAME 0.281+**, Neo-Geo WRAM entity perception, and a **Mixture of Experts (MoE)** policy architecture.
Through a 9-action Semi-Markov Decision Process (SMDP) intent space and character-specialized policies (multi-round sequences + closed-loop distance-reactive controllers), AI **Haohmaru** achieves **16/16 full-roster Best-of-3 (Bo3) victories** on live MAME emulation.

---

## 🌟 Key Features

- **🏆 16/16 Full Roster Cleared (Bo3 Verified)**: Defeats all 16 opponents—including final boss **Rashoujin Mizuki**, **Genjuro**, **Ukyo**, **Jubei**, **Charlotte**, **Sieger**, and the **Haohmaru** mirror match—in full Best-of-3 matches.
- **🎮 True 2P VS Human vs. AI Mode**: Automatically triggers the arcade *"Here Comes a New Challenger"* 2P join into character select. AI locks 1P Haohmaru (`JOY1` only, 1P keyboard disabled to prevent input conflicts); you freely pick **any** 2P character with pre-configured `WASD + J/K/L/U/I/O` controls (plus arrow/numpad fallback) and a 15-second post-match victory screen.
- **⚡ Direct WRAM Entity Perception**: Reads authoritative logical health (`UID + 0xBB`), character coordinates, character ID (`UID + E_CHAR`), and hit-latch registers directly from Neo-Geo memory, eliminating pixel-bar lag and camera zoom artifacts.
- **📹 Automated 60 FPS MP4 + Bilingual Subtitle Pipeline**: Captures lossless MAME video (`-aviwrite`), transcodes to H.264/AAC MP4 via FFmpeg, and generates synchronized Chinese/English `.srt` subtitles plus millisecond-accurate `_commentary.json` event timelines.
- **🧠 Isolated MoE Policy Architecture**: Each opponent has an independent JSON policy under `models/experts/vs_<opponent>.json` supporting both per-round sequences and closed-loop distance-reactive policies (`DistanceReactivePolicy`).
- **📚 Comprehensive Engineering & Digital Asset Docs**: Includes full technical reports, video asset usage guides, and a concrete MoE-to-PPO/Offline-RL training roadmap (`finaldoc/` and `finaldoc/en/`).

---

## 🚀 Quick Start

> [!IMPORTANT]
> **Legal & Resource Disclaimer**: This repository does **NOT** include MAME emulator binaries, copyrighted game ROMs (`samsho2.zip`), or Neo-Geo BIOS files (`neogeo.zip`). Users must legally obtain MAME and game ROM/BIOS files independently. This project is provided strictly for reinforcement learning research and educational demonstration.

### 1. Set Up Python Environment (Windows 64-bit, Python 3.10–3.13)
```powershell
# 1. Clone the repository
git clone https://github.com/footballqq/samsho2-moe-ai.git
cd samsho2-moe-ai

# 2. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies (optional: install CUDA PyTorch first per requirements.txt)
pip install -r requirements.txt
```

### 2. Configure MAME & Legally Obtained ROM/BIOS
- Download **MAME 0.281+ (64-bit Windows)** from [mamedev.org](https://www.mamedev.org/) and extract it either to a sibling folder `mame0281b_x64`, or point to it via `$env:MAME_DIR = "C:\path\to\mame0281b_x64"`.
- Place your legally obtained `samsho2.zip` and `neogeo.zip` inside MAME's `roms\` directory.

### 3. Watch AI Spectator Demos
```powershell
.\play_demo.ps1
# Or double-click play_demo.cmd
```
Select an opponent (`1`–`16`) from the interactive menu, or launch directly:
```powershell
.\play_demo.ps1 -Target genjuro -Mode bo3
```

### 4. Challenge the AI (True 2P VS Mode)
```powershell
# AI plays 1P Haohmaru vs. Human freely picking ANY 2P character
.\play_demo.ps1 -Target genjuro -Human
```
- **Default 2P Controls (auto-installed)**: `W/A/S/D` movement, `J/K/L` Light/Medium/Heavy Slash (`L = A+B`), `U/I/O` Light/Medium/Heavy Kick (`O = C+D`), with Arrow Keys + Numpad `1–6` also active.
- Once the match starts, the system reads your chosen 2P character ID from WRAM and automatically switches AI Haohmaru to the matching counter-expert.

### 5. Record 60 FPS MP4 Match Videos & Bilingual Subtitles
Requires **FFmpeg** available in your system `PATH`:
```powershell
# Record a single Bo3 victory video (outputs MP4 + _zh.srt + _en.srt + _commentary.json)
.\record_video.ps1 -Target charlotte

# Batch record all 16 opponents (auto-skips already verified Bo3 videos)
.\record_video.ps1 -All
```

---

## 📊 16/16 Full Roster Bo3 Verification Matrix

| # | Opponent | Key | Bo3 Score | Status | Policy Type & Core Strategy |
| :-: | :--- | :--- | :-: | :-: | :--- |
| 01 | **Earthquake** | `earthquake` | 2 - 1 | ✅ VERIFIED | Jump-in pressure + crouch-guard punish |
| 02 | **Genjuro Kibagami** | `genjuro` | 2 - 0 | ✅ VERIFIED | Banner guard delay + anti-air vs. Triple Slash |
| 03 | **Galford** | `galford` | 2 - 0 | ✅ VERIFIED | Opening guard timing + anti-air vs. Poppy rush |
| 04 | **Nakoruru** | `nakoruru` | 2 - 0 | ✅ VERIFIED | Grounded poke + slash loop vs. hawk dive |
| 05 | **Cham Cham** | `chamcham` | 2 - 1 | ✅ VERIFIED | Timing-shifted slash counter vs. boomerang |
| 06 | **Wan-Fu** | `wanfu` | 2 - 1 | ✅ VERIFIED | Heavy slash whiff-punish vs. pillar slam |
| 07 | **Neinhalt Sieger** | `sieger` | 2 - 1 | ✅ VERIFIED | Closed-loop distance-reactive anti-air & slash |
| 08 | **Senryo Kyoshiro** | `kyoshiro` | 2 - 0 | ✅ VERIFIED | Jump-in pressure into blind-spot heavy slash |
| 09 | **Hanzo Hattori** | `hanzo` | 2 - 1 | ✅ VERIFIED | Fast poke interrupt vs. teleport & command grab |
| 10 | **Gen-An Shiranui** | `genan` | 2 - 0 | ✅ VERIFIED | Guard-poke spacing vs. poison breath & slide |
| 11 | **Nicotine Caffeine** | `nicotine` | 2 - 0 | ✅ VERIFIED | Guard seal talisman + close-range heavy cleave |
| 12 | **Rashoujin Mizuki** | `mizuki` | 2 - 0 | ✅ VERIFIED | Closed-loop distance-reactive rushdown vs. boss zoning |
| 13 | **Haohmaru (Mirror)** | `haowmaru` | 2 - 1 | ✅ VERIFIED | Tempo-shifted guard & counter-slash mirror |
| 14 | **Ukyo Tachibana** | `ukyo` | 2 - 1 | ✅ VERIFIED | Opening guard vs. afterimage + heavy cleave |
| 15 | **Yagyu Jubei** | `jubei` | 2 - 1 | ✅ VERIFIED | Double-slash + guard loop breaking close pokes |
| 16 | **Charlotte** | `charlotte` | 2 - 1 | ✅ VERIFIED | Rising crescent anti-air + fireball follow-up |

---

## 📄 Technical Paper

A complete two-column system & empirical methodology paper documenting this architecture, BUG-17/18 postmortems, and 16/16 experimental results is included under `paper/`:
- **English PDF (6 pages, IEEE/arXiv style)**: [paper/samsho2_moe_paper.pdf](paper/samsho2_moe_paper.pdf) (LaTeX source: [samsho2_moe_paper.tex](paper/samsho2_moe_paper.tex))
- **Chinese PDF (中文版, 4 pages)**: [paper/samsho2_moe_paper_zh.pdf](paper/samsho2_moe_paper_zh.pdf) (Source: [samsho2_moe_paper_zh.tex](paper/samsho2_moe_paper_zh.tex) / [HTML](paper/samsho2_moe_paper_zh.html))

---

## 📚 Documentation (`finaldoc/en/` & `finaldoc/`)

### English Technical Documentation Suite (`finaldoc/en/`, 10/10 Complete)
- [00. Overview & Repository Navigation](finaldoc/en/00_Overview_and_Navigation.md)
- [01. Project Lifecycle: From the PPO Impasse to a 16/16 MoE Clean Sweep](finaldoc/en/01_Project_Lifecycle_From_PPO_to_MoE_Sweep.md)
- [02. Technical Route Evaluation: PPO, HELT League, Monolithic Nets vs. MoE](finaldoc/en/02_Technical_Route_Evaluation_PPO_HELT_and_Monolithic.md)
- [03. Match Replay Assets & Offline Learning Value Guide](finaldoc/en/03_Match_Replay_Assets_and_Offline_RL_Guide.md)
- [04. Human vs. AI Real-Time Deployment & Operations Guide](finaldoc/en/04_Human_vs_AI_Deployment_and_Operations_Guide.md)
- [05. Open-Source Repository Architecture & Release Build Guide](finaldoc/en/05_Open_Source_Repo_Architecture_and_Release_Guide.md)
- [07. Video Capture & Multimodal Commentary Generation Pipeline](finaldoc/en/07_Video_Capture_and_Multimodal_Commentary_Pipeline.md)
- [08. Video Editor & Digital Asset Usage Guide (16/16 Master Manifest)](finaldoc/en/08_Video_Editor_and_Digital_Asset_Guide.md)
- [09. Compilation Video Production Postmortem & Playbook](finaldoc/en/09_Compilation_Video_Production_Postmortem_and_Playbook.md)
- [10. MoE-to-PPO & Advanced RL Training Roadmap](finaldoc/en/10_MoE_to_PPO_and_Advanced_RL_Roadmap.md)

### Full Chinese Technical Monographs (`finaldoc/`)
- [00. 总览与全景导航](finaldoc/00_总览与全景导航.md)
- [01. 全生命周期实录：从 PPO 困境到 MoE 全员通关](finaldoc/01_项目全生命周期实录_从PPO困境到MoE全员通关.md)
- [02. 技术路线评估：PPO、HELT 联赛与大一统网络对比](finaldoc/02_技术路线评估与深度剖析_PPO_HELT联赛与大一统网络.md)
- [03. 对局录像资产与未来离线学习价值指南](finaldoc/03_对局录像资产与未来离线学习价值指南.md)
- [04. 人机对战实机部署与实操指南](finaldoc/04_人机对战实机部署与实操指南.md)
- [05. 开源 Repo 架构设计与发布构建指南](finaldoc/05_开源Repo架构设计与发布构建指南.md)
- [07. 录像制作与多模态解说生成流水线说明](finaldoc/07_录像制作与多模态解说生成流水线说明.md)
- [08. 专业视频剪辑师指南与数字资产使用手册](finaldoc/08_专业视频剪辑师指南与资产使用手册.md)
- [09. 合集视频制作实战复盘与踩坑手册](finaldoc/09_合集视频制作实战复盘_脚本参数与踩坑手册.md)
- [10. MoE 资产反哺 PPO 与强化学习进阶训练路线指南](finaldoc/10_MoE资产反哺PPO与强化学习进阶训练路线指南.md)

---

## 📜 License
This project's source code and documentation are released under the [MIT License](LICENSE). See `LICENSE` for the game asset & emulator scope notice.
