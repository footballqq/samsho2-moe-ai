# 08. Video Editor & Digital Asset Usage Guide (16/16 Complete Edition)

> **Location**: `finaldoc/en/08_Video_Editor_and_Digital_Asset_Guide.md`  
> **Chinese Counterpart**: [../08_专业视频剪辑师指南与资产使用手册.md](../08_专业视频剪辑师指南与资产使用手册.md)  
> **Target Audience**: Video editors, content creators, esports commentators, and multimodal AI researchers consuming the exported `videos/` assets.

---

## 1. Opening Narration Script (For Intro 0:00–0:45)

> *"In the golden age of arcade fighting games, SNK's iconic masterpiece **Samurai Shodown II** stood as the pinnacle of weapon-based combat—renowned for razor-sharp neutral spacing, frame-perfect whiff punishes, and high-stakes lethality.*  
> *Today, powered by Deep Reinforcement Learning and a Mixture of Experts (MoE) architecture, the legendary swordsman **Haohmaru** awakens as a fully autonomous combat intelligence.*  
> *Through direct WRAM perception and structured tactical search, AI Haohmaru conquered all 16 roster opponents in full Best-of-3 matches—from the vicious ferocity of Genjuro and the illusions of Hanzo, all the way to the demonic sorcery of final boss Mizuki.*  
> *Sit back and witness modern artificial intelligence forge a new legend in the timeless art of the blade!"*

---

## 2. Asset Package Structure & Technical Specifications

Each recorded match in `videos/` is delivered as a synchronized 5-file bundle:

```text
videos/
 ├── <timestamp>_haohmaru_vs_<opponent>_VICTORY.mp4             # 60 FPS H.264/AAC match video
 ├── <timestamp>_haohmaru_vs_<opponent>_VICTORY_en.srt          # English SubRip commentary subtitles
 ├── <timestamp>_haohmaru_vs_<opponent>_VICTORY_zh.srt          # Chinese SubRip commentary subtitles
 ├── <timestamp>_haohmaru_vs_<opponent>_VICTORY.srt             # Default subtitle track (ZH compatible)
 └── <timestamp>_haohmaru_vs_<opponent>_VICTORY_commentary.json # Millisecond event timeline & metadata
```

| Specification | Value | Notes |
| :--- | :--- | :--- |
| **Video Codec** | H.264 / AVC (`libx264`, CRF 20) | Universally compatible with Premiere, DaVinci, FCP, CapCut |
| **Pixel Format** | `yuv420p` | Standard 8-bit 4:2:0 color, zero import color-shift |
| **Frame Rate** | **59.19 FPS** (Neo-Geo native 60 FPS clock) | Smooth arcade motion with authentic hitstop frames |
| **Audio** | AAC Stereo, 44.1 kHz, 128 kbps | Full original arcade SFX & BGM |
| **Victory Hold** | **18.0 seconds** post-KO | Captures sword sheathing, victory quote, and final score screen |

---

## 3. How to Use These Digital Assets (4 Practical Workflows)

### Workflow A: Direct Playback & Live Presentations
- Open any `.mp4` in **VLC**, **MPV**, or **PotPlayer** with the matching `_en.srt` or `_zh.srt` in the same folder.
- Switch subtitle tracks in your player menu for instant bilingual commentary during demos or talks.

### Workflow B: Hard-Burning Subtitles for YouTube / Shorts / TikTok / Bilibili
Many social platforms ignore external `.srt` files. Burn subtitles directly into the video with FFmpeg while keeping 60 FPS quality:

```powershell
# Burn English subtitles (YouTube / X / Reddit)
ffmpeg -i "20261123_133024_haohmaru_vs_mizuki_VICTORY.mp4" `
  -vf "subtitles='20261123_133024_haohmaru_vs_mizuki_VICTORY_en.srt':force_style='FontName=Arial,FontSize=18,Outline=2'" `
  -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a copy "mizuki_en_burnin.mp4"

# Burn Chinese subtitles (Bilibili / Douyin / WeChat Channels)
ffmpeg -i "20261123_133024_haohmaru_vs_mizuki_VICTORY.mp4" `
  -vf "subtitles='20261123_133024_haohmaru_vs_mizuki_VICTORY_zh.srt':force_style='FontName=Microsoft YaHei,FontSize=20,Outline=2'" `
  -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a copy "mizuki_zh_burnin.mp4"
```

### Workflow C: Programmatic Highlight Slicing via `_commentary.json`
Every `_commentary.json` records structured segments (`MATCH_START`, `MID_COMBAT`, `INTERMISSION`, `KO_FINISH`, `CELEBRATION_SHEATHE`, `CELEBRATION_QUOTE`) with exact `start_sec` / `end_sec`. Automatically clip the final 15-second KO + celebration for a montage:

```python
import json, subprocess

meta = json.load(open("20261123_135611_haohmaru_vs_sieger_VICTORY_commentary.json", encoding="utf-8"))
ko_events = [s for s in meta.get("segments", []) if s.get("event_type") == "KO_FINISH"]
if ko_events:
    t0 = max(0.0, ko_events[-1]["start_sec"] - 3.0)
    subprocess.run([
        "ffmpeg", "-y", "-ss", f"{t0:.2f}",
        "-i", "20261123_135611_haohmaru_vs_sieger_VICTORY.mp4",
        "-t", "15", "-c", "copy", "sieger_ko_highlight.mp4"
    ])
```

### Workflow D: Multimodal AI Research & Local Reproduction
- **Vision-Language Benchmarks**: Pair the 60 FPS MP4 frames with `_commentary.json` (bilingual play-by-play + round scores + timestamps) to evaluate or fine-tune video-understanding VLMs on fighting-game commentary.
- **Re-Recording Locally**: With MAME and your own ROM/BIOS configured, run `.\record_video.ps1 -Target mizuki` or `.\record_video.ps1 -All` to regenerate any video locally at custom bitrates or resolutions.

---

## 4. Verified 16/16 Master Asset Manifest

All 16 videos below passed physical quality gating (`mode=bo3`, `final_score in {2-0, 2-1}`, `hold_duration_sec=18.0s`, bilingual SRT + JSON verified):

| # | Opponent | Score | Duration | Size | Verified Master Filename (`videos/`) |
| :-: | :--- | :-: | :-: | :-: | :--- |
| 1 | Earthquake (`earthquake`) | 2-1 | 146.0s | 30.13 MB | `20261122_185614_haohmaru_vs_earthquake_VICTORY.mp4` |
| 2 | Genjuro (`genjuro`) | 2-0 | 79.5s | 20.15 MB | `20261122_172942_haohmaru_vs_genjuro_VICTORY.mp4` |
| 3 | Galford (`galford`) | 2-0 | 90.6s | 16.77 MB | `20261122_190548_haohmaru_vs_galford_VICTORY.mp4` |
| 4 | Nakoruru (`nakoruru`) | 2-0 | 105.8s | 19.97 MB | `20261123_122050_haohmaru_vs_nakoruru_VICTORY.mp4` |
| 5 | Cham Cham (`chamcham`) | 2-1 | 118.1s | 21.04 MB | `20261123_122301_haohmaru_vs_chamcham_VICTORY.mp4` |
| 6 | Wan-Fu (`wanfu`) | 2-1 | 122.1s | 26.46 MB | `20261122_195536_haohmaru_vs_wanfu_VICTORY.mp4` |
| 7 | Sieger (`sieger`) | 2-1 | 123.7s | 19.50 MB | `20261123_135611_haohmaru_vs_sieger_VICTORY.mp4` |
| 8 | Kyoshiro (`kyoshiro`) | 2-0 | 92.0s | 17.27 MB | `20261122_200623_haohmaru_vs_kyoshiro_VICTORY.mp4` |
| 9 | Hanzo (`hanzo`) | 2-1 | 93.2s | 13.55 MB | `20261123_123343_haohmaru_vs_hanzo_VICTORY.mp4` |
| 10 | Gen-An (`genan`) | 2-0 | 95.6s | 19.90 MB | `20261122_201432_haohmaru_vs_genan_VICTORY.mp4` |
| 11 | Nicotine (`nicotine`) | 2-0 | 100.1s | 15.69 MB | `20261123_123537_haohmaru_vs_nicotine_VICTORY.mp4` |
| 12 | Mizuki (`mizuki`) | 2-0 | 78.7s | 19.23 MB | `20261123_133024_haohmaru_vs_mizuki_VICTORY.mp4` |
| 13 | Haohmaru (`haowmaru`) | 2-1 | 113.9s | 20.78 MB | `20261123_124449_haohmaru_vs_haowmaru_VICTORY.mp4` |
| 14 | Ukyo (`ukyo`) | 2-1 | 117.5s | 17.30 MB | `20261122_203851_haohmaru_vs_ukyo_VICTORY.mp4` |
| 15 | Jubei (`jubei`) | 2-1 | 109.3s | 19.14 MB | `20261123_124706_haohmaru_vs_jubei_VICTORY.mp4` |
| 16 | Charlotte (`charlotte`) | 2-1 | 136.5s | 22.94 MB | `20261122_204757_haohmaru_vs_charlotte_VICTORY.mp4` |
