"""WRAM bulk dump + diff scanning helpers (T4/T5 core machinery).

Bulk read design: CONFIG carries N=u32 entries sweeping 0x100000..0x10FFFC
step 4 (16384 entries); every STATE then returns the whole 64KB WRAM as
65,536 bytes (16384 x u32) plus the observation set. Lockstep makes each
dump frame-exact.

Bridge CONFIG entries come from build_wram_dump_entries(); remember to send
CONFIG before first action (MameBridge does it in __init__ — pass entries).
"""
from __future__ import annotations

import struct

from mame_types import TYPE_U32

WRAM_BASE = 0x100000
WRAM_SIZE = 0x10000


def build_wram_dump_entries(step: int = 4) -> list[tuple[int, int]]:
    return [(a, TYPE_U32) for a in range(WRAM_BASE, WRAM_BASE + WRAM_SIZE, step)]


def wram_from_state(values: tuple[int, ...], step: int = 4) -> bytes:
    """u32 STATE values -> 64KB WRAM bytes (little endian, address order)."""
    return struct.pack(f"<{len(values)}I", *values)


class FrameDumper:
    """Records consecutive frame dumps in memory; diffs against a baseline."""

    def __init__(self, bridge, step: int = 4):
        self.bridge = bridge
        self.step = step
        self.frames: list[bytes] = []

    def grab(self, frames: int = 1) -> None:
        for _ in range(frames):
            vals, _f = self.bridge.action(step_frames=1)
            self.frames.append(wram_from_state(vals, self.step))

    def changed_addresses(self, baseline: int = 0) -> list[int]:
        """Addresses whose u32 changed vs frame `baseline` in ANY later frame."""
        if len(self.frames) <= baseline + 1:
            return []
        base = self.frames[baseline]
        out = []
        for off in range(0, len(base), 4):
            for f in self.frames[baseline + 1:]:
                if f[off:off + 4] != base[off:off + 4]:
                    out.append(WRAM_BASE + off)
                    break
        return out
