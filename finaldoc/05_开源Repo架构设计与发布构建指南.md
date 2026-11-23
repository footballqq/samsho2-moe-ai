# 侍魂2 开源 Repo 架构设计、发布构建与外部使用全指南

> **归档位置**: `finaldoc\05_开源Repo架构设计与发布构建指南.md`  
> **核心目标**: 针对“如何将内部研发项目打包发布为高水准 GitHub 开源项目”，提供干净利落的代码目录规范、自动化清洗导出脚本、外部开发者快速上手手册、以及即开即用的官方 README.md 范本。

---

## 一、开源仓库的定位与目录架构

### 1.1 仓库定位
- **项目名称**: `samsho2-moe-ai` (或 `SamuraiShodownII-Agent`)
- **一句话定义**: 首个在 Neo-Geo / MAME 经典格斗街机《侍魂2》中达成全员 16 位对手 100% 击破的轻量级混合专家（MoE）与人机对战 AI 系统。
- **核心卖点**:
  - **零门槛即开即玩**: 一键运行 `play_demo.ps1`，即可在 MAME 窗口观战霸王丸大破 16 位对手；
  - **支持真人手柄对抗**: 外接手柄或副键盘，随时进入人机对决模式与 AI 大师切磋；
  - **一键录制高清 MP4**: 内置自动化录屏与转码流水线，生成 60 FPS H.264 比赛视频；
  - **学术与离线学习底座**: 提供全套因果对局日志，支持离线强化学习（Offline RL）与行为克隆（BC）。

### 1.2 干净发布版的推荐目录树 (Zero-Junk Layout)
由于内部迭代中积累了上百个探索性测试脚本（`diag_*.py`, `sweep_*.py`），在正式发布到 GitHub 前必须进行工程清洗。清洗后的标准开源目录如下：

```text
samsho2-moe-ai/
├── README.md                      # GitHub 顶级主页说明 (特性、架构图、安装与运行指南)
├── requirements.txt               # 极简 Python 依赖包 (torch, gymnasium, sb3 等)
├── play_demo.ps1                  # 核心体验交互入口 (观战、人机对战、录制)
├── play_demo.cmd                  # Windows 双击运行跳板 (无需敲命令行)
├── record_video.ps1               # 一键批量录制 MP4 脚本
│
├── src/                           # 生产级核心源码
│   ├── demo_player.py             # 交互式观战与对战播放器
│   ├── mame_moe.py                # MoE 混合专家路由器与策略加载器
│   ├── bo3_controller.py          # 三局两胜 (Bo3) 状态机与局间时延守卫
│   ├── moe_roster.py              # 16 位对手元数据与动作语义字典
│   ├── mame_client.py             # MAME 模拟器 TCP Socket 通信客户端
│   ├── mame_gym.py                # Gymnasium 标准格斗环境实现
│   ├── mame_hitbox.py             # 物理碰撞盒 (Hitbox) 与攻击距离判定表
│   └── train_rl.py                # 强化学习与自动求解器训练入口
│
├── models/experts/                # 16 位对手全胜专家模型资产
│   ├── manifest.json              # 官方验收清单与战绩元数据 (16/16 Verified)
│   ├── vs_earthquake.json         # 地震专家配置
│   ├── vs_genjuro.json            # 牙神专家配置
│   └── ... (共 16 份角色特化配置)
│
├── mame/                          # 模拟器端桥接文件
│   └── bridge.lua                 # MAME Lua 引擎底层 TCP 通信与内存钩子脚本
│
├── data/mame/instance/rl/state/samsho2/  # 角色初始状态锚点 (.sta 关键帧)
│   ├── earthquake.sta
│   ├── mizuki.sta
│   └── ... (共 16 个对手对战锚点)
│
├── tools/                         # 实用维护与打包工具
│   ├── record_match_mp4.py        # MAME -aviwrite + FFmpeg 转码自动化工具
│   └── export_clean_repo.ps1      # 自动化清洗导出打包脚本
│
└── finaldoc/                      # 专著级技术总结与复盘文档集
    ├── 00_总览与全景导航.md
    ├── 01_项目全生命周期实录_从PPO困境到MoE全员通关.md
    ├── 02_技术路线评估与深度剖析_PPO_HELT联赛与大一统网络.md
    ├── 03_对局录像资产与未来离线学习价值指南.md
    ├── 04_人机对战实机部署与实操指南.md
    └── 05_开源Repo架构设计与发布构建指南.md
```

---

## 二、一键自动清洗与导出工具 (`export_clean_repo.ps1`)

为了避免手动挑选文件的繁琐与遗漏，我们编写了专用的自动化导出脚本 `tools/export_clean_repo.ps1`。  
只需在 PowerShell 中运行：
```powershell
.\tools\export_clean_repo.ps1
```
脚本会自动在 `dist/samsho2_ai_release/` 目录中生成一份完全独立的、纯净的、无任何冗余测试日志的成品仓库。您可以直接将该目录整体推送到 GitHub：
```powershell
cd dist\samsho2_ai_release
git init
git add .
git commit -m "feat: initial open-source release of Samurai Shodown II MoE AI"
git remote add origin https://github.com/footballqq/samsho2-moe-ai.git
git push -u origin main
```

---

## 三、外部用户安装与快速上手指南 (Quickstart Guide)

一位完全未接触过本项目的开发者，只需遵循以下 4 步即可在 5 分钟内完整运行：

### 步骤 1：克隆项目与安装 Python 环境
确保本机安装了 Python 3.10 ~ 3.12 (64-bit)：
```powershell
# 1. 克隆代码仓库
git clone https://github.com/footballqq/samsho2-moe-ai.git
cd samsho2-moe-ai

# 2. 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. 安装依赖包
pip install -r requirements.txt
```

### 步骤 2：下载 MAME 模拟器与配置 ROM 资源
1. **下载 MAME 官方版本**:
   - 前往 MAME 官方网站下载 MAME 0.281 或更新版本的 64 位 Windows 解压包（解压至例如 `C:\path\to\mame0281b_x64`）；
   - 或者设置系统环境变量 `MAME_DIR` 指向你的 MAME 安装根目录。
2. **放置游戏 ROM 与 BIOS**:
   - 将《侍魂2》正版 ROM `samsho2.zip` 与 Neo-Geo 基础 BIOS `neogeo.zip` 放入 MAME 的 `roms/` 目录下。

### 步骤 3：一键启动交互式观战演示
无需任何复杂配置，直接在 PowerShell 中执行：
```powershell
.\play_demo.ps1
```
程序会打印出包含 16 位已击破对手的动态菜单，输入 `1` 到 `16` 选择任意对手（如 `16: 夏洛特`、`12: 罗将神水姬`、`14: 橘右京`），MAME 窗口会自动弹起，以真实 60 FPS 街机原速呈现霸王丸的斩杀演示与 10 秒胜利结算！

### 步骤 4：进入实机手柄对战 (Human vs AI)
想要亲自拿起手柄和 AI 霸王丸切磋：
```powershell
# 在命令行直达对战，例如操控牙神幻十郎迎战霸王丸
.\play_demo.ps1 -Target genjuro -Human
```
或者在 `.\play_demo.ps1` 交互菜单中输入体验选项 `2`，便可使用外接手柄操控 2P 角色进行实机对抗。

### 步骤 5：一键录制 MP4 比赛视频
如果你想将打赢 Boss 罗将神的精彩比赛录制为高清 MP4 视频分享给朋友：
```powershell
# 自动以 2 倍速录制打罗将神的决胜局并输出 MP4
.\record_video.ps1 -Target mizuki

# 或者一键批量把全员 16 个人的比赛全部录成 MP4 视频
.\record_video.ps1 -All
```
生成的录像将自动存放于 `videos/` 目录下，采用标准的 H.264 / AAC 编码，体积仅几兆，可在微信、B站、手机端流畅播放。

---

## 四、官方 GitHub README.md 范本

以下是为您准备好的高质量、国际化 GitHub 顶级 `README.md` 完整范本：

```markdown
# ⚔️ Samurai Shodown II: MoE Autonomous Fighter AI
### 侍魂2 混合专家自主格斗智能体系统

[![Platform](https://img.shields.io/badge/Platform-Neo--Geo%20%7C%20MAME-red.svg)](#)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](#)
[![Architecture](https://img.shields.io/badge/Architecture-SMDP%20%7C%20MoE-orange.svg)](#)
[![Status](https://img.shields.io/badge/Roster%20Cleared-16%2F16%20Verified%20(100%25)-brightgreen.svg)](#)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](#)

A high-performance, lightweight Mixture-of-Experts (MoE) AI agent for the legendary arcade fighter **Samurai Shodown II (真SAMURAI SPIRITS 覇王丸地獄変)**. Built on top of MAME WRAM reverse-engineering and Semi-Markov Decision Process (SMDP) tactical search, this AI achieves a **100% verified win rate across all 16 arcade opponents in continuous Best-of-3 matches**.

---

## 🌟 Key Features

- **🏆 16/16 Full Roster Conquered**: 100% continuous Best-of-3 victory against all 16 fighters, including the final boss Mizuki, Ukyo, Genjuro, Jubei, Charlotte, and the Haohmaru mirror match.
- **🎮 Real-Time Human vs. AI Combat**: Plug in your USB gamepad or keyboard and fight directly against the AI Master in a live 60 FPS MAME window.
- **⚡ Zero-Lag Hardware WRAM Perception**: Direct Neo-Geo memory read (`0xBB` real HP, hitboxes, character states), completely bypassing pixel display lag and HUD camera zoom blinding.
- **📹 One-Click 60 FPS MP4 Video Recording**: Integrated MAME capture and FFmpeg pipeline to record full match demonstrations into crisp, compact H.264 MP4 videos.
- **🧠 Modular MoE Architecture**: Specialized, decoupled expert policies for each fighter. Updating one opponent never degrades performance against the other 15!
- **🔬 Comprehensive Academic Research Suite**: Includes 5 exhaustive research monographs on PPO pitfalls, HELT self-play leagues, and Offline Reinforcement Learning.

---

## 🚀 Quick Start (5 Minutes)

### 1. Prerequisites
- Windows 10/11 (64-bit)
- Python 3.10 ~ 3.12
- [MAME 0.281](https://www.mamedev.org/) or newer
- Neo-Geo BIOS (`neogeo.zip`) & Samurai Shodown II ROM (`samsho2.zip`) placed inside MAME's `roms/` folder.

### 2. Installation
```powershell
git clone https://github.com/footballqq/samsho2-moe-ai.git
cd samsho2-moe-ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Watch Spectator Demo
```powershell
.\play_demo.ps1
```
Choose any opponent (1-16) from the interactive menu and watch Haohmaru execute precise strikes, anti-air jumps, and frame-perfect punishes!

### 4. Challenge the AI (Human vs AI)
```powershell
# Challenge Haohmaru using Player 2 (e.g. Genjuro)
.\play_demo.ps1 -Target genjuro -Human
```

### 5. Record MP4 Video
```powershell
# Record a 60 FPS match video against Charlotte or Mizuki
.\record_video.ps1 -Target charlotte
```

---

## 📊 16/16 Verified Roster Status

| # | Opponent | Archetype | Bo3 Score | Status | Key Counter-Strategy |
|---|---|---|:---:|:---:|---|
| 01 | **Earthquake** | Giant Grappler | 2 - 1 | ★ VERIFIED | Jump-slash pressure + low guard punish |
| 02 | **Genjuro** | Rival Swordsman | 2 - 1 | ★ VERIFIED | Delay guard + anti-air punish on Tri-Slash |
| 03 | **Galford** | Ninja & Dog | 2 - 0 | ★ VERIFIED | 32-step banner hold + jump anti-air |
| 04 | **Nakoruru** | Fast Aerial | 2 - 1 | ★ VERIFIED | Ground poke spacing + hawk punish |
| 05 | **Kyoshiro** | Naginata Dancer | 2 - 0 | ★ VERIFIED | Double jump over reach + heavy slash |
| 06 | **Gen-an** | Demon Slayer | 2 - 0 | ★ VERIFIED | Poke guard against poison + close slash |
| 07 | **Nicotine** | Exorcist Monk | 2 - 0 | ★ VERIFIED | Staff spacing + seal talisman evasion |
| 08 | **Mizuki (Boss)** | Evil Deity | 2 - 1 | ★ VERIFIED | Rushdown strike + anti-air anti-pig hex |
| 09 | **Hanzo** | Iga Ninja | 2 - 0 | ★ VERIFIED | Rapid poke counter-grab + clone intercept |
| 10 | **Wan-fu** | Stone Pillar | 2 - 1 | ★ VERIFIED | Spacing poke + aerial smash counter-rush |
| 11 | **Sieger** | Iron Arm Knight | 2 - 0 | ★ VERIFIED | Heavy poke spacing against close grabs |
| 12 | **Haohmaru** | Mirror Match | 2 - 0 | ★ VERIFIED | 40-step cadence disruption + punish |
| 13 | **Cham Cham** | Wild Boomerang | 2 - 0 | ★ VERIFIED | Burst approach + bidirectional return parry |
| 14 | **Ukyo** | Iaijutsu Master | 2 - 0 | ★ VERIFIED | 4-step block vs dash + double jump over snow |
| 15 | **Jubei** | Dual Katana | 2 - 0 | ★ VERIFIED | Double crouch approach + wave counter |
| 16 | **Charlotte** | Rapier Fencer | 2 - 0 | ★ VERIFIED | Anti-air Crescent Moon + fireball slash |

---

## 📚 Technical Documentation

Deep dive into the architecture, mathematical formulations, and engineering post-mortems in our `finaldoc/` directory:
- [00. Overview & Architecture Navigation](finaldoc/00_总览与全景导航.md)
- [01. Full Engineering Lifecycle: From PPO Impasse to MoE Breakthrough](finaldoc/01_项目全生命周期实录_从PPO困境到MoE全员通关.md)
- [02. Comparative Analysis: PPO, HELT Self-Play Leagues, vs. Monolithic Networks](finaldoc/02_技术路线评估与深度剖析_PPO_HELT联赛与大一统网络.md)
- [03. Match Recording Assets & Future Offline Reinforcement Learning Guide](finaldoc/03_对局录像资产与未来离线学习价值指南.md)
- [04. Real-time Human vs. AI Battle Operation Manual](finaldoc/04_人机对战实机部署与实操指南.md)
- [05. Open-Source Repo Architecture & Release Guide](finaldoc/05_开源Repo架构设计与发布构建指南.md)

---

## 📜 License
Distributed under the MIT License. See `LICENSE` for more information.
```
