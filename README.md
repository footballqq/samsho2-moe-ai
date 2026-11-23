# ⚔️ Samurai Shodown II: MoE Autonomous Fighter AI
### 侍魂2 混合专家自主格斗智能体系统

**语言 / Language**: **中文** | [English](README_EN.md)

[![Platform](https://img.shields.io/badge/Platform-Neo--Geo%20%7C%20MAME-red.svg)](#)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](#)
[![Architecture](https://img.shields.io/badge/Architecture-SMDP%20%7C%20MoE-orange.svg)](#)
[![Status](https://img.shields.io/badge/Roster%20Cleared-16%2F16%20Verified%20(100%25)-brightgreen.svg)](#)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](#)

基于 **MAME 0.281 模拟器** 与 **混合专家系统 (Mixture of Experts, MoE)** 的经典格斗街机《真侍魂：霸王丸地狱变》自主智能体系统。
通过底层 Neo-Geo WRAM 实体内存逆向与半马尔可夫决策（SMDP）意图空间组合优化，实现了**全员 16 位对手连续三局两胜 (Best-of-3) 100% 独立实机击破验证**！

---

## 🌟 核心特性 (Key Features)

- **🏆 16/16 全员对手 100% 击破**: 包含最终终极 Boss 罗将神水姬、橘右京、牙神幻十郎、柳生十兵卫、夏洛特以及霸王丸同门镜像，全部通过实机连续 Bo3 决胜验证！
- **🎮 真人实时对抗 (Human vs AI)**: 支持 `-Human`（真人 1P 霸王丸 vs AI 2P）与 `-HumanP2`（真人 2P vs AI 1P），开箱自动加载 `WASD` 方向 + `J/K/L/U/I/O` 攻击键位，也支持 USB 手柄。
- **⚡ 底层 WRAM 实体感知**: 直读 Neo-Geo 物理内存（`0xBB` 逻辑血量、角色坐标与命中锁存器），避免像素血条 HUD 延迟与镜头放缩干扰。
- **📹 一键录制 60 FPS MP4 高清对决与双语字幕**: 内置 MAME 帧捕获、FFmpeg 转码与双语解说引擎，一键输出 H.264/AAC MP4 视频、`_zh.srt` / `_en.srt` 字幕及结构化时间轴 JSON。
- **🧠 物理级隔离 MoE 专家架构**: 每位对手拥有独立 JSON 专家策略配置（支持多回合序列与基于实体距离的闭环策略），针对单个对手优化绝不破坏其他 15 位对手的稳定性。
- **📚 全套技术研制与数字资产文档**: `finaldoc/` 包含完整的研发复盘、路线评估、人机实操与视频数字资产使用手册。

---

## 🚀 快速开始 (Quick Start)

> [!IMPORTANT]
> **资源与版权声明**：本仓库**不包含** MAME 模拟器二进制文件，也**不包含**任何受版权保护的游戏 ROM（`samsho2.zip`）或 BIOS（`neogeo.zip`）。运行前请自行合法获取 MAME 模拟器与游戏 ROM/BIOS，本项目仅用于强化学习研究与教学演示。

### 1. 准备 Python 环境
确保安装 64 位 Python 3.10 ~ 3.13（Windows PowerShell）：
```powershell
# 1. 克隆项目（请替换为你的仓库地址）
git clone https://github.com/footballqq/samsho2-moe-ai.git
cd samsho2-moe-ai

# 2. 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. 安装依赖包（如需 GPU 加速可先按 requirements.txt 注释安装对应 CUDA 版 PyTorch）
pip install -r requirements.txt
```

### 2. 配置 MAME 模拟器与 ROM（需用户自行准备）
- 前往 [MAME 官网](https://www.mamedev.org/) 下载解压 **MAME 0.281 或更新版本（64 位 Windows）**，放置于同级目录 `mame0281b_x64`（或设置环境变量 `$env:MAME_DIR = "C:\path\to\mame0281b_x64"`）；
- 将合法获取的《侍魂2》ROM `samsho2.zip` 与 Neo-Geo BIOS `neogeo.zip` 放入 MAME 的 `roms\` 目录下。

### 3. 一键启动交互式观战演示
```powershell
.\play_demo.ps1
# 或直接双击 play_demo.cmd
```
在交互菜单中输入 `1` 到 `16` 选择任意对手，或直接命令行指定（例如 `.\play_demo.ps1 -Target genjuro -Mode bo3`），MAME 窗口将自动弹起呈现完整 Bo3 对局。

### 4. 挑战 AI (真·双人 VS 人机对决模式)
```powershell
# 启动「AI 控 1P 霸王丸 vs 真人控 2P 任意自选角色」双人 VS 对决
.\play_demo.ps1 -Target genjuro -Human
```
> 启动后自动触发街机 **2P 乱入** 进入双人选人界面：AI 自动锁定 1P 霸王丸（1P 键盘已屏蔽防抢键），你用 `W/A/S/D + J` 自由挑选任意角色作为 2P 迎战；开战后 AI 会自动读取你选的角色并切换对应专家策略！
> 默认键盘映射：`W/A/S/D` 方向，`J/K/L` 轻/中/重斩，`U/I/O` 轻/中/重踢（同时兼容方向键 + 小键盘 `1~6`）。

### 5. 一键生成 60 FPS MP4 比赛视频与双语字幕
需先安装 **FFmpeg** 并确保 `ffmpeg` 在系统 `PATH` 中：
```powershell
# 录制单场 Bo3 决胜录像（输出 MP4 + 中英双语 SRT + 结构化 JSON）
.\record_video.ps1 -Target charlotte

# 批量录制全部 16 位对手
.\record_video.ps1 -All
```

---

## 📊 全员 16 位对手最终验收矩阵

| 序号 | 对手角色 | 英文标识 | Bo3 最终比分 | 验收状态 | 核心克制战术 |
| :---: | :--- | :--- | :---: | :---: | :--- |
| 01 | **地震** | `earthquake` | 2 - 1 | ★ VERIFIED | 先手双起跳下砸压制 + 决胜局下防确反 |
| 02 | **牙神幻十郎** | `genjuro` | 2 - 1 | ★ VERIFIED | 局间时延防守 + 升龙确反破三连杀 |
| 03 | **加尔福特** | `galford` | 2 - 0 | ★ VERIFIED | 32步横幅防 + 空中拦截破忍犬 |
| 04 | **娜可露露** | `nakoruru` | 2 - 1 | ★ VERIFIED | 地面刺击破神鹰突刺 + 稳固拉扯 |
| 05 | **千两狂死郎** | `kyoshiro` | 2 - 0 | ★ VERIFIED | 双起跳压制薙刀盲区 + 大劈破火炎 |
| 06 | **不知火幻庵** | `genan` | 2 - 0 | ★ VERIFIED | 试探防守破毒吹息 + 贴身连斩确反 |
| 07 | **花讽院和仲** | `nicotine` | 2 - 0 | ★ VERIFIED | 稳健格挡避封魔符 + 重斩破长杖 |
| 08 | **罗将神水姬 (Boss)** | `mizuki` | 2 - 1 | ★ VERIFIED | 地震级先手压制 + 对空破防破变猪邪法 |
| 09 | **服部半藏** | `hanzo` | 2 - 0 | ★ VERIFIED | 连续快刺打断莫迦投 + 升龙破影分身 |
| 10 | **王虎** | `wanfu` | 2 - 1 | ★ VERIFIED | 刺斩破石柱猛劈 + 纵跳下砸破肉弹 |
| 11 | **莱因哈特** | `sieger` | 2 - 0 | ★ VERIFIED | 破防重刺控距 + 贴身防擒拿抱摔 |
| 12 | **霸王丸 (同门镜像)** | `haowmaru` | 2 - 0 | ★ VERIFIED | 40步变频打乱 + 重刀确反同门弧月斩 |
| 13 | **查姆查姆** | `chamcham` | 2 - 0 | ★ VERIFIED | 突进变频斩 + 时钟延顺双向反打回旋镖 |
| 14 | **橘右京** | `ukyo` | 2 - 0 | ★ VERIFIED | 开局4步格挡防残像 + 双跳大劈破细雪 |
| 15 | **柳生十兵卫** | `jubei` | 2 - 0 | ★ VERIFIED | 双防逼近确反斩 + 稳扎稳打破水月刀 |
| 16 | **夏洛特** | `charlotte` | 2 - 0 | ★ VERIFIED | 升龙弧月斩拦截跳刺 + 发波二段大劈破西洋剑 |

---

## 📚 专著级技术研制与复盘文档集 (`finaldoc/`)

深度技术细节、数学公式与系统工程复盘请查阅 `finaldoc/` 专著集合：
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

## 📜 许可证 (License)
本项目代码采用 [MIT 许可证](LICENSE) 开源发布。
