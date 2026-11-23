# 05. Open-Source Repository Architecture & Release Build Guide

> **Location**: `finaldoc/en/05_Open_Source_Repo_Architecture_and_Release_Guide.md`  
> **Chinese Counterpart**: [../05_开源Repo架构设计与发布构建指南.md](../05_开源Repo架构设计与发布构建指南.md)

---

## 1. Repository Positioning & Clean Release Layout

The public release (`dist/samsho2_ai_release/`) strips away internal scratch scripts, debug probes, and raw logs, delivering a self-contained open-source package built around **23 whitelisted production Python modules**:

```text
samsho2-moe-ai/
├── README.md / README_EN.md          # Bilingual top-level guides
├── LICENSE                           # MIT License + ROM/BIOS/Emulator disclaimer
├── requirements.txt                  # Minimal Python runtime dependencies
├── .gitignore                        # Release-specific (preserves tools/ and 17 .sta anchors)
├── play_demo.ps1 / play_demo.cmd     # Spectator & True 2P VS launcher
├── record_video.ps1 / .cmd           # 60 FPS MP4 & bilingual subtitle recorder
├── mame/bridge.lua                   # MAME Lua TCP bridge
├── src/                              # 23 whitelisted production modules (AST-verified closure)
├── tools/
│   ├── record_match_mp4.py           # MAME -aviwrite + FFmpeg + CommentaryEngine
│   └── export_clean_repo.ps1         # Maintainer clean-release packager
├── models/experts/                   # 16 verified vs_<char>.json + manifest.json (no legacy files)
├── data/mame/
│   ├── cfg/                          # Pre-configured WASD + JKL/UIO keybinding templates
│   ├── movesets/haohmaru.yaml        # SMDP macro definitions
│   └── instance/rl/state/samsho2/    # 17 round-start savestate anchors (.sta)
└── finaldoc/                         # Full Chinese & English (finaldoc/en/) documentation
```

---

## 2. Maintainer Export Pipeline (`tools/export_clean_repo.ps1`)

Run from the source repository to regenerate a clean, publishable release snapshot:
```powershell
.\tools\export_clean_repo.ps1
```
What the exporter guarantees:
1. **Strict `src/` Whitelist**: Copies only the 23 AST-verified production modules (excludes legacy WinKawaks scripts, `diag_*`, `test_*`, and `scratch_*`).
2. **Legacy Model Exclusion**: Copies `manifest.json` and all 16 verified `vs_<char>.json` experts while skipping `*legacy*` files.
3. **Runtime Assets Bundled**: Copies `mame/bridge.lua`, `data/mame/movesets/*.yaml`, `data/mame/cfg/*.cfg`, and all 17 `.sta` anchors.
4. **Release-Safe `.gitignore`**: Dynamically writes a clean `.gitignore` that ignores `.venv/`, `logs/`, `videos/`, and runtime instances while explicitly preserving `tools/` and `data/mame/instance/rl/state/samsho2/*.sta`.
5. **Bilingual Docs**: Exports both `finaldoc/*.md` and `finaldoc/en/*.md`, plus `README.md`, `README_EN.md`, and `LICENSE`.

### Publishing to GitHub
```powershell
cd dist\samsho2_ai_release
git init
git add .
git commit -m "feat: initial open-source release of Samurai Shodown II MoE AI"
git remote add origin https://github.com/footballqq/samsho2-moe-ai.git
git push -u origin main
```

---

## 3. External User Prerequisites & Quickstart

> **Disclaimer**: No MAME binaries, ROMs (`samsho2.zip`), or Neo-Geo BIOS (`neogeo.zip`) are distributed in this repository. Users must obtain them legally and independently.

1. **Python 3.10–3.13 (64-bit Windows)**: `python -m venv .venv`, activate, and run `pip install -r requirements.txt`.
2. **MAME 0.281+**: Extract beside the repo as `mame0281b_x64` or set `$env:MAME_DIR`. Place `samsho2.zip` and `neogeo.zip` in MAME's `roms/`.
3. **FFmpeg** *(optional, for MP4 recording only)*: Ensure `ffmpeg` and `ffprobe` are on your system `PATH`.
4. **Launch**: Run `.\play_demo.ps1` (spectator / True 2P VS) or `.\record_video.ps1 -Target charlotte` (MP4 recording).
