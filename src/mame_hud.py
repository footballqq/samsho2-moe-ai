"""HUD bar reader: P1/P2 HP from screen pixels (ground truth, verified).

Bar geometry (320x224, confirmed 2026-11-05):
  P1 bar: x 16..143, y 19..26  (128px = full HP)
  P2 bar: x 176..303, y 19..26 (128px)
Green-ish pixel count / row-normalized to bar length -> HP estimate
(quantization ±2 HP at 160 max).

read_bars(data, w, h) takes MAME XRGB frame bytes (B,G,R,X order).
"""
from __future__ import annotations

# WIDE windows: bars are per-character LENGTH (~0.8px per HP point,
# e.g. Ukyo 164 -> ~132px drawn); the old x176..303 window clipped longer
# bars. Split at x152 so the two zones never overlap.
P1_BAR = (8, 152, 19, 27)    # x0, x1, y0, y1
P2_BAR = (152, 312, 19, 27)
BAR_FULL_PX = 128.0          # legacy reference only (BarReader auto-calibrates)


def _count_green(data: bytes, w: int, x0: int, x1: int, y0: int, y1: int) -> int:
    cnt = 0
    for y in range(y0, y1):
        base = y * w * 4
        for x in range(x0, x1):
            o = base + x * 4
            b, g, r = data[o], data[o + 1], data[o + 2]
            if g > 120 and g > r + 40 and g > b + 40:
                cnt += 1
    return cnt


def count_bars(data: bytes, w: int, h: int) -> tuple[int, int]:
    """RAW green-pixel counts for both bars (no normalization)."""
    return _count_green(data, w, *P1_BAR), _count_green(data, w, *P2_BAR)


def read_bars(data: bytes, w: int, h: int) -> tuple[float, float]:
    """Legacy fixed-128px ratios (only correct for 128-stamina chars)."""
    c1, c2 = count_bars(data, w, h)
    return c1 / (BAR_FULL_PX * 8), c2 / (BAR_FULL_PX * 8)


class BarReader:
    """Per-round HP-bar reader, correct for ANY character stamina.

    SS2 bars are per-character LENGTH (stamina px): a fixed 128px window
    normalizes wrong (Sieger 186 clips to 1.0 until 69% HP). And the
    near-fight CAMERA ZOOM moves/hides the HUD: both counts vanish at once —
    that is NOT a double KO.

    Usage: read() auto-calibrates each side's full count as the running max
    over the first CALIB_FRAMES reads (HP refill grows the bar), then locks.
    Both-vanish holds the last reading; single-side vanish counts toward
    KO detection as before.
    """

    CALIB_FRAMES = 20

    def __init__(self):
        self.full = [1.0, 1.0]
        self._n = 0
        self.last = (0.0, 0.0)

    def read(self, c1: int, c2: int) -> tuple[float, float]:
        c = (max(c1, 0), max(c2, 0))
        if self._n < self.CALIB_FRAMES:
            self.full[0] = max(self.full[0], c[0])
            self.full[1] = max(self.full[1], c[1])
            self._n += 1
        r1 = min(c[0] / self.full[0], 1.0) if self.full[0] > 0 else 0.0
        r2 = min(c[1] / self.full[1], 1.0) if self.full[1] > 0 else 0.0
        # HUD hidden (zoom/cutscene): BOTH vanish while both were alive
        if r1 <= 0.02 and r2 <= 0.02 and self.last[0] > 0.05 and self.last[1] > 0.05:
            return self.last                    # hold; not a double KO
        self.last = (r1, r2)
        return self.last
