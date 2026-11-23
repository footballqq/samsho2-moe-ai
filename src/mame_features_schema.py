"""Versioned feature schema registry for entity observations (R5 stage A / Task 1).

Single source of truth for the entity-observation layout: per-frame
channel names/indices, stacking order, and derived indices for stacked
observations. Consumers MUST derive indices from here instead of hard-
coding them.

Layout (per frame, appended in this order):
  base25 : dx_signed, dist, p1_bar, p2_bar, m1, m2, s1, s2,
           p2 flags x6 (air/hit/block/punish/down/up),
           p1 flags x6 (same order), d1, d2, p2_char, timer, camera
  y      : p1_y, p2_y                                    (frame 27)
  hitbox : p1_reach, p2_threat, tip_margin, in_threat, throwable
                                                          (frame 32)
Stacked observation = [prev_frame | curr_frame]; the CURRENT-frame
timer therefore sits at frame_width + TIMER_IN_FRAME:
  48 (50d) / 50 (54d) / 55 (64d).

Pure data + pure functions — no bridge/env imports.
"""
from __future__ import annotations

SCHEMA_VERSION = "2026-11-19-r5-a1"   # bump on any layout change
OBS_SEMANTICS_VERSION = "wram_authoritative_v1"  # health & feature semantic version
REWARD_VERSION = "reward_wram_v1"                # reward calculation version

TIMER_IN_FRAME = 23                   # timer position inside each frame

BASE_CHANNELS = [{"name": n, "index": i} for i, n in enumerate([
    "dx_signed", "dist", "p1_bar", "p2_bar", "meter1", "meter2",
    "stun1", "stun2",
    "p2_air", "p2_hit", "p2_block", "p2_punish", "p2_down", "p2_up",
    "p1_air", "p1_hit", "p1_block", "p1_punish", "p1_down", "p1_up",
    "dir1", "dir2", "p2_char", "timer", "camera"])]

Y_CHANNELS = [{"name": n, "index": 25 + i}
              for i, n in enumerate(["p1_y", "p2_y"])]

HITBOX_CHANNELS = [{"name": n, "index": 27 + i}
                   for i, n in enumerate(["p1_reach", "p2_threat",
                                          "tip_margin", "in_threat",
                                          "throwable"])]


def frame_width(n_hitbox_channels: int, with_y: bool = True) -> int:
    """Per-frame width for a given hitbox channel count (0 = no hitbox).
    The y block is always present in the entity families we version
    (50d is the historical no-y layout: frame_width(0, with_y=False)=25)."""
    width = 25 + (2 if with_y else 0) + n_hitbox_channels
    return width


def stacked_size(frame_width_: int) -> int:
    """Two-frame stacked observation size."""
    return frame_width_ * 2


def stacked_timer_index(frame_width_: int) -> int:
    """Index of the CURRENT-frame timer inside the stacked observation."""
    return frame_width_ + TIMER_IN_FRAME


def y_block(frame_width_: int) -> tuple[int, int]:
    """(start, stop) slice of the y channels inside one frame."""
    return 25, 27


def hitbox_block(frame_width_: int) -> tuple[int, int]:
    """(start, stop) slice of the hitbox channels inside one frame
    (they are the last channels of the frame)."""
    return frame_width_ - 5, frame_width_


def channel_index(name: str, frame_width_: int) -> int:
    """Resolve a channel name to its per-frame index for a frame width.
    Raises KeyError when the channel does not exist in that layout."""
    for c in BASE_CHANNELS:
        if c["name"] == name:
            return c["index"]
    if name in {c["name"] for c in Y_CHANNELS} and frame_width_ >= 27:
        return 25 + ["p1_y", "p2_y"].index(name)
    if name in {c["name"] for c in HITBOX_CHANNELS} and frame_width_ >= 32:
        return 27 + ["p1_reach", "p2_threat", "tip_margin", "in_threat",
                     "throwable"].index(name)
    raise KeyError(f"channel {name!r} not in frame width {frame_width_}")


def input_permutation(old_dim: int, new_dim: int) -> list[int]:
    """Semantic input permutation for weight transplant: old column i
    maps to new column perm[i].

    Both layouts share the frame structure [base25 | y2 | hitbox...]
    with y appended after base and hitbox appended last; the permutation
    keeps base channels in place per frame and shifts the y block to the
    new base width (hitbox channels have no old counterpart — new columns
    they would occupy are simply not referenced by old weights).

    Examples:
      54 -> 64 : [0..26 stay] + [27..53 -> 32..58]
      50 -> 54 : [0..25 stay] + [25..49 -> 27..51]
      50 -> 64 : [0..25 stay] + [25..49 -> 32..56]
    """
    pairs = {
        (50, 54): (25, 27),
        (50, 64): (25, 32),
        (54, 64): (27, 32),
    }
    if old_dim == new_dim:
        return list(range(old_dim))
    if (old_dim, new_dim) not in pairs:
        raise ValueError(f"unsupported transplant {old_dim}->{new_dim}")
    old_frame, new_frame = pairs[(old_dim, new_dim)]
    n_frames = old_dim // old_frame
    return [frame * new_frame + off
            for frame in range(n_frames)
            for off in range(old_frame)]
