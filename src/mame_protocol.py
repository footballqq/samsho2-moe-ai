"""Wire protocol between Python and mame/bridge.lua.

Framing (both directions, little-endian): [u8 opcode][u32 payload_len][payload].
Pure stdlib (struct); constants live in mame_types.py.
"""
from __future__ import annotations

import socket
import struct

from mame_types import (MSG_ERR, MSG_HELLO, OP_CONFIG, TYPE_CODES)

_HEADER = struct.Struct("<BI")


class BridgeError(RuntimeError):
    pass


def pack_msg(op: int, payload: bytes = b"") -> bytes:
    return _HEADER.pack(op, len(payload)) + payload


def pack_config(playing_addr: int, playing_value: int,
                ready_delay: int, ready_timeout: int,
                entries: list[tuple[int, int]]) -> bytes:
    # entry count is u32 (bulk WRAM dumps use >16k entries)
    payload = struct.pack("<IBHHI", playing_addr, playing_value,
                          ready_delay, ready_timeout, len(entries))
    for addr, type_code in entries:
        payload += struct.pack("<IB", addr, type_code)
    return pack_msg(OP_CONFIG, payload)


def pack_action(dir_mask: int, btn_mask: int, press_frames: int,
                step_frames: int, want_pixels: bool = False) -> bytes:
    return pack_msg(2, struct.pack("<BBBBB", dir_mask, btn_mask,
                                   press_frames, step_frames, int(want_pixels)))


def pack_press(role: int, mask: int, press_frames: int, wait_frames: int,
               want_pixels: bool = False) -> bytes:
    return pack_msg(3, struct.pack("<BBHHB", role, mask, press_frames,
                                   wait_frames, int(want_pixels)))


def pack_load_state(name: str, want_pixels: bool = False) -> bytes:
    return pack_msg(4, struct.pack("<B", int(want_pixels)) + name.encode())


def pack_save_state(name: str) -> bytes:
    return pack_msg(5, name.encode())


def pack_set(key: str, value: str) -> bytes:
    return pack_msg(6, f"{key}={value}".encode())


def pack_write(addr: int, type_code: int, value: int) -> bytes:
    return pack_msg(9, struct.pack("<IBi", addr, type_code, value))


def pack_read(addr: int, type_code: int) -> bytes:
    """OP_READ: dynamic single-point memory read (uid-relative entity reads)."""
    return pack_msg(11, struct.pack("<IB", addr, type_code))


def pack_readf(role: int = 0, mask: int | None = None) -> bytes:
    body = struct.pack("<B", role)
    if mask is not None:
        body += struct.pack("<B", mask)
    return pack_msg(10, body)


def parse_hello(payload: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in payload.decode(errors="replace").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
    return out


def parse_state_values(payload: bytes, n_vars: int) -> tuple[int, ...]:
    # unsigned u32 wire format; signed types are sign-extended by Lua and
    # arrive as 2^32-complements (mask at call sites when needed)
    return struct.unpack_from(f"<{n_vars}I", payload, 0)


def recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks: list[bytes] = []
    remaining = n
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise BridgeError("bridge socket closed by MAME")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def recv_msg(sock: socket.socket) -> tuple[int, bytes]:
    op, length = _HEADER.unpack(recv_exact(sock, _HEADER.size))
    payload = recv_exact(sock, length) if length else b""
    if op == MSG_ERR:
        raise BridgeError(f"bridge error: {payload.decode(errors='replace')}")
    return op, payload


def parse_hello_hello(hello: dict[str, str]) -> dict[str, str]:
    """Alias kept for readability at call sites."""
    return hello


assert MSG_HELLO == 100 and OP_CONFIG == 1 and TYPE_CODES["u16"] == 2
