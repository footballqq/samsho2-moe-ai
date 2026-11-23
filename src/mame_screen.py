"""Screen capture helpers for the SS2 bridge (XRGB frames -> PNG)."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

from mame_client import MameBridge


def png_bytes_from_xrgb(data: bytes, w: int, h: int) -> bytes:
    """MAME RGB32 is XRGB words; little-endian memory order = B,G,R,X per pixel."""
    stride = w * 3
    raw = bytearray(stride * h)
    for i in range(w * h):
        s = i * 4
        d = i * 3
        raw[d] = data[s + 2]      # R
        raw[d + 1] = data[s + 1]  # G
        raw[d + 2] = data[s]      # B
    rows = bytearray()
    for y in range(h):
        rows.append(0)  # filter type 0
        rows += raw[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (len(payload).to_bytes(4, "big") + tag + payload
                + zlib.crc32(tag + payload).to_bytes(4, "big"))

    ihdr = w.to_bytes(4, "big") + h.to_bytes(4, "big") + bytes([8, 2, 0, 0, 0])
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b""))


def grab_png(bridge: MameBridge, path: Path) -> tuple[int, ...]:
    """Advance 1 frame with pixels on, save PNG, return the STATE values."""
    vals, frame = bridge.action(dir_mask=0, press_frames=0, step_frames=1,
                                want_pixels=True)
    if frame:
        w, h, data = frame
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png_bytes_from_xrgb(data, w, h))
    return vals
