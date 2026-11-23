"""Generate publication-quality 300-DPI figures and real gameplay montage for the paper."""
from __future__ import annotations

import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from PIL import Image, ImageDraw, ImageFont

PAPER_DIR = Path(r"E:\games\SamuraiShodownII_moe\paper")
FIG_DIR = PAPER_DIR / "figures"
VIDEO_DIR = Path(r"E:\games\SamuraiShodownII_moe\videos")
FIG_DIR.mkdir(parents=True, exist_ok=True)


def make_fig1_architecture() -> None:
    """Fig. 1: Four-layer system architecture diagram (WRAM -> SMDP -> MoE -> Bo3/VS)."""
    fig, ax = plt.subplots(figsize=(10.5, 4.6), dpi=300)
    ax.set_xlim(0, 10.5)
    ax.set_ylim(0, 4.6)
    ax.axis("off")

    def box(x, y, w, h, title, body, fc, ec, title_color="#111827"):
        rect = patches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.06,rounding_size=0.12",
            linewidth=1.5, edgecolor=ec, facecolor=fc
        )
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h - 0.24, title, ha="center", va="top",
                fontsize=9.2, fontweight="bold", color=title_color, family="DejaVu Sans")
        ax.text(x + w / 2, y + h - 0.52, body, ha="center", va="top",
                fontsize=7.6, color="#1f2937", family="DejaVu Sans", linespacing=1.35)

    # Layer 1: Emulation & Hardware Bridge
    box(0.2, 2.75, 2.85, 1.55,
        "1. MAME 0.281 + Lua Bridge",
        "Neo-Geo samsho2 (59.19 Hz)\nTCP Lockstep & -video gdi\nWRAM Direct Memory Read:\nUID: 0x100A46 / 0x100A4A\nHP: UID+0xBB | Char: 0x00..0x10",
        "#EFF6FF", "#2563EB", "#1E3A8A")

    # Layer 2: SMDP Gym Environment
    box(3.55, 2.75, 3.15, 1.55,
        "2. SS2RoundEnv (SMDP)",
        "25-D Entity Obs (2-frame stack)\nNormalized |dx|/512 & Hit Latch\n9 Semantic Combat Intents (0..8):\nAPPROACH, POKE, SLASH, GUARD,\nANTI_AIR, PUNISH, FIREBALL, JUMP",
        "#F0FDF4", "#16A34A", "#14532D")

    # Layer 3: MoE Policy Router
    box(7.2, 2.75, 3.1, 1.55,
        "3. Isolated MoE Router",
        "Static WRAM Opponent-ID Routing\n16 Verified JSON Experts (vs_*.json)\n• PerRoundPolicy (R1 vs R2/R3)\n• SequencePolicy (14 Matchups)\n• DistanceReactivePolicy (Mizuki/Sieger)",
        "#FFF7ED", "#EA580C", "#7C2D12")

    # Layer 4A: Physical-Invariant Bo3 Arbiter
    box(1.3, 0.35, 3.7, 1.65,
        "4A. Physical-Invariant Bo3 Arbiter",
        "Bo3MatchController (BUG-17 / BUG-18 Guarded)\n• Sustained KO: zs >= 3 consecutive steps\n• Asymmetric Loser Refill: streak >= 8 steps\n• Intermission Floor >= 60 steps; Round Floor >= 25\n• Never awards timeout false victories",
        "#FEF2F2", "#DC2626", "#7F1D1D")

    # Layer 4B: Deployment & Multimodal Outputs
    box(5.55, 0.35, 4.45, 1.65,
        "4B. Evaluation, Recording & True 2P VS",
        "• Automated 60 FPS MP4 + FFmpeg (16/16 Verified)\n• Adaptive Bilingual Commentary (_zh/_en.srt + JSON)\n• 18.0s Post-KO Victory Celebration Verification\n• True 2P VS Mode (Auto 2P Challenger Join,\n  AI owns JOY1, Human owns JOY2 WASD+JKLUIO)",
        "#F5F3FF", "#7C3AED", "#4C1D95")

    arrow_kw = dict(arrowstyle="-|>,head_width=0.22,head_length=0.28", lw=1.6, color="#374151")
    # Horizontal top arrows
    ax.annotate("", xy=(3.53, 3.68), xytext=(3.07, 3.68), arrowprops=arrow_kw)
    ax.text(3.3, 3.82, "WRAM", ha="center", va="bottom", fontsize=7.0, color="#374151")
    ax.annotate("", xy=(3.07, 3.32), xytext=(3.53, 3.32), arrowprops=arrow_kw)
    ax.text(3.3, 3.10, "JOY1", ha="center", va="top", fontsize=7.0, color="#374151")

    ax.annotate("", xy=(7.18, 3.68), xytext=(6.72, 3.68), arrowprops=arrow_kw)
    ax.text(6.95, 3.82, "obs", ha="center", va="bottom", fontsize=7.0, color="#374151")
    ax.annotate("", xy=(6.72, 3.32), xytext=(7.18, 3.32), arrowprops=arrow_kw)
    ax.text(6.95, 3.10, "intent", ha="center", va="top", fontsize=7.0, color="#374151")

    # Down arrows to Bo3 arbiter & outputs
    ax.annotate("", xy=(3.6, 2.04), xytext=(4.6, 2.73), arrowprops=arrow_kw)
    ax.text(3.7, 2.38, "HP / bars", ha="center", va="center", fontsize=7.0, color="#374151")

    ax.annotate("", xy=(8.3, 2.73), xytext=(4.5, 2.04),
                arrowprops=dict(arrowstyle="-|>,head_width=0.22,head_length=0.28", lw=1.4, ls="--", color="#DC2626"))
    ax.text(6.6, 2.25, "round_just_started / IDLE lock", ha="center", va="center", fontsize=7.0, color="#991B1B")

    ax.annotate("", xy=(5.53, 1.18), xytext=(5.02, 1.18), arrowprops=arrow_kw)
    ax.text(5.28, 1.33, "verdict", ha="center", va="bottom", fontsize=6.8, color="#374151")

    plt.tight_layout(pad=0.2)
    out = FIG_DIR / "fig1_architecture.png"
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("Saved:", out)


def make_fig2_gameplay_montage() -> None:
    """Fig. 2: 2x3 montage of real 60 FPS gameplay frames extracted from verified Bo3 MP4s."""
    samples = [
        ("20261123_133024_haohmaru_vs_mizuki_VICTORY.mp4", 42.0, "vs. Mizuki (Boss, 2-0, Reactive)"),
        ("20261123_135611_haohmaru_vs_sieger_VICTORY.mp4", 98.0, "vs. Sieger (2-1, Reactive)"),
        ("20261122_172942_haohmaru_vs_genjuro_VICTORY.mp4", 55.0, "vs. Genjuro (2-0, Per-Round)"),
        ("20261122_185614_haohmaru_vs_earthquake_VICTORY.mp4", 120.0, "vs. Earthquake (2-1, Per-Round)"),
        ("20261123_124706_haohmaru_vs_jubei_VICTORY.mp4", 82.0, "vs. Jubei (2-1, Per-Round)"),
        ("20261122_204757_haohmaru_vs_charlotte_VICTORY.mp4", 112.0, "vs. Charlotte (2-1, Per-Round)"),
    ]
    thumbs = []
    tmp_dir = FIG_DIR / "_tmp_frames"
    tmp_dir.mkdir(exist_ok=True)
    for idx, (fname, ts, label) in enumerate(samples):
        mp4 = VIDEO_DIR / fname
        out_png = tmp_dir / f"frame_{idx}.png"
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-ss", f"{ts:.1f}",
            "-i", str(mp4), "-frames:v", "1", str(out_png)
        ], check=True)
        img = Image.open(out_png).convert("RGB")
        thumbs.append((img, label))

    fig, axes = plt.subplots(2, 3, figsize=(10.2, 5.2), dpi=300)
    for ax, (img, label) in zip(axes.flat, thumbs):
        ax.imshow(img)
        ax.set_title(label, fontsize=9.0, fontweight="bold", pad=4, family="DejaVu Sans")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_edgecolor("#374151")
            spine.set_linewidth(1.0)
    plt.tight_layout(pad=0.6)
    out = FIG_DIR / "fig2_gameplay_montage.png"
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    # Clean temporary frames
    for p in tmp_dir.glob("*.png"):
        p.unlink()
    tmp_dir.rmdir()
    print("Saved:", out)


def make_fig3_roster_performance() -> None:
    """Fig. 3: Verified 16-opponent Bo3 match duration, score (2-0 vs 2-1), and policy type."""
    # Ground-truth ffprobe durations & scores verified 2026-11-23
    data = [
        ("Mizuki (Boss)", 78.7, "2-0", "Reactive"),
        ("Genjuro",       79.5, "2-0", "Sequence"),
        ("Galford",       90.6, "2-0", "Sequence"),
        ("Kyoshiro",      92.0, "2-0", "Sequence"),
        ("Hanzo",         93.2, "2-1", "Sequence"),
        ("Gen-An",        95.6, "2-0", "Sequence"),
        ("Nicotine",     100.1, "2-0", "Sequence"),
        ("Nakoruru",     105.8, "2-0", "Sequence"),
        ("Jubei",        109.3, "2-1", "Sequence"),
        ("Haohmaru",     113.9, "2-1", "Sequence"),
        ("Ukyo",         117.5, "2-1", "Sequence"),
        ("Cham Cham",    118.1, "2-1", "Sequence"),
        ("Wan-Fu",       122.1, "2-1", "Sequence"),
        ("Sieger",       123.7, "2-1", "Reactive"),
        ("Charlotte",    136.5, "2-1", "Sequence"),
        ("Earthquake",   146.0, "2-1", "Sequence"),
    ]
    names = [d[0] for d in data]
    durs = [d[1] for d in data]
    scores = [d[2] for d in data]
    ptypes = [d[3] for d in data]

    colors = []
    for sc, pt in zip(scores, ptypes):
        if pt == "Reactive":
            colors.append("#EA580C")  # Orange for closed-loop reactive
        elif sc == "2-0":
            colors.append("#2563EB")  # Blue for 2-0 sequence sweep
        else:
            colors.append("#0D9488")  # Teal for 2-1 sequence victory

    fig, ax = plt.subplots(figsize=(8.6, 4.8), dpi=300)
    y = np.arange(len(names))
    bars = ax.barh(y, durs, color=colors, height=0.68, edgecolor="#1F2937", linewidth=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8.8, family="DejaVu Sans")
    ax.invert_yaxis()
    ax.set_xlabel("Verified 60 FPS Bo3 Recording Duration (seconds, incl. 18.0s Victory Hold)",
                  fontsize=9.0, family="DejaVu Sans")
    ax.set_xlim(0, 168)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    for bar, dur, sc, pt in zip(bars, durs, scores, ptypes):
        tag = f"{dur:.1f}s ({sc})" + (" [Reactive]" if pt == "Reactive" else "")
        ax.text(dur + 1.8, bar.get_y() + bar.get_height() / 2, tag,
                va="center", ha="left", fontsize=7.8, color="#111827", family="DejaVu Sans")

    legend_handles = [
        patches.Patch(facecolor="#2563EB", edgecolor="#1F2937", label="Per-Round Sequence (2-0 Sweep, n=6)"),
        patches.Patch(facecolor="#0D9488", edgecolor="#1F2937", label="Per-Round Sequence (2-1 Win, n=8)"),
        patches.Patch(facecolor="#EA580C", edgecolor="#1F2937", label="Closed-Loop Distance-Reactive (n=2)"),
    ]
    ax.legend(handles=legend_handles, loc="lower right", fontsize=8.0, frameon=True)
    ax.set_title("16/16 Full-Roster Verified Best-of-3 Victory Durations & Policy Types",
                 fontsize=10.2, fontweight="bold", pad=8, family="DejaVu Sans")

    plt.tight_layout(pad=0.4)
    out = FIG_DIR / "fig3_roster_performance.png"
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("Saved:", out)


if __name__ == "__main__":
    make_fig1_architecture()
    make_fig2_gameplay_montage()
    make_fig3_roster_performance()
