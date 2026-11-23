# 07. Video Capture & Multimodal Commentary Generation Pipeline

> **Location**: `finaldoc/en/07_Video_Capture_and_Multimodal_Commentary_Pipeline.md`  
> **Chinese Counterpart**: [../07_录像制作与多模态解说生成流水线说明.md](../07_录像制作与多模态解说生成流水线说明.md)

---

## 1. End-to-End Pipeline Architecture

`tools/record_match_mp4.py` automates the full lifecycle from MAME emulation to publish-ready multimodal video bundles:

```text
  MoEAgent (Intent 0..8)
          │
          ▼
  MAME 0.281 (-video gdi -aviwrite) ──► Lua WRAM Bridge ──► Bo3MatchController
          │ (raw 60 FPS AVI)                                       │ (step events)
          ▼                                                        ▼
  FFmpeg (libx264 / AAC)                                  CommentaryEngine
          │                                               (adaptive ZH/EN pacing)
          └──────────────────────┬─────────────────────────────────┘
                                 ▼
              Publish-Ready Multimodal Bundle (videos/):
                • <match_id>_VICTORY.mp4
                • <match_id>_VICTORY_zh.srt / _en.srt / .srt
                • <match_id>_VICTORY_commentary.json
```

---

## 2. Reliable Capture Engineering (`-video gdi` + `speed=1`)

- **Why `-video gdi`**: Default Direct3D (`-video d3d`) can trigger GPU TDR/device-lost crashes during unattended background runs or screen lock. Software GDI rendering (`-video gdi`) paired with `-aviwrite` pulls frame-exact 59.19 FPS video and 44.1 kHz stereo PCM directly from MAME with zero driver hangs.
- **Native 1x Speed (`--speed 1`)**: Video capture always runs at 1x native clock so internal timers, hitstop frames, and audio streams remain 100% synchronized.

---

## 3. FFmpeg Transcoding Specification

Raw MAME AVI files exceed 1 GB per Bo3 match. The pipeline immediately transcodes and deletes the temporary AVI:
```bash
ffmpeg -y -i temp_match.avi \
  -c:v libx264 -pix_fmt yuv420p -preset fast -crf 20 \
  -c:a aac -b:a 128k \
  output_match_VICTORY.mp4
```
- `crf=20` preserves sharp arcade pixel clarity at ~13–30 MB per full Bo3 match.
- `yuv420p` guarantees playback compatibility across Windows, macOS, browsers, and all NLE editors.

---

## 4. Bo3 Lifecycle & 18-Second Victory Celebration Capture

1. **Round-by-Round Arbitration (`Bo3MatchController`)**: Tracks sustained zero-HP KOs (`zs >= 3`), intermission `IDLE` locking, asymmetric round refills, and `round_just_started` notifications to `PerRoundPolicy`.
2. **18-Second Post-Match Hold**: Once a fighter reaches 2 round wins (`2-0` or `2-1`), the recorder forces `throttle_rate=1` and advances empty frames for **18.0 seconds**, capturing Haohmaru's sword sheathing, sake-drinking celebration, victory quote, and final score screen.
3. **Smart `--skip-existing`**: Batch recording (`--all`) inspects existing `_commentary.json` files and skips only verified Bo3 videos (`mode == "bo3"`, `final_score in ("2-0", "2-1")`, `hold_duration_sec >= 15.0`).

---

## 5. Adaptive Bilingual Commentary Engine (`src/commentary_engine.py`)

- **Time Conversion**: Anchored to Neo-Geo's native refresh rate (`59.1856 FPS`, 2 frames per environment step):
  $$t_{\text{sec}} = \frac{\text{step} \times 2}{59.1856}$$
- **Adaptive Pacing (`fit_text`)**: Selects among short, medium, and long commentary variants to match natural esports narration density (~4.2 Chinese chars/sec or equivalent English cadence) without overlapping cues.
- **Narrative Arc**: Automatically structures each Bo3 match into Opening Intro → Round 1 Combat → Intermission → Deciding Round KO (`KO_FINISH`) → 3-Stage Victory Celebration (`CELEBRATION_SHEATHE`, `CELEBRATION_QUOTE`, Final Score).
