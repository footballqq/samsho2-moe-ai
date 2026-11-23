"""Lock-step TCP client for mame/bridge.lua (Python = server, MAME = client).

One MameBridge owns: the listening socket (dynamic port), the MAME process,
the handshake (HELLO/CONFIG) and the whole command vocabulary.
"""
from __future__ import annotations

import socket
import struct
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent

from mame_process import MameProcess
from mame_protocol import (BridgeError, _HEADER, pack_action, pack_config,
                           pack_load_state, pack_msg, pack_press, pack_read,
                           pack_readf, pack_save_state, pack_set, pack_write,
                           parse_hello, parse_state_values, recv_exact,
                           recv_msg)
from mame_types import MSG_HELLO, MSG_OK, MSG_PONG, MSG_READY, MSG_STATE, OP_PING, OP_QUIT

# T2 placeholder observation set (T4 replaces with the verified spec):
# P1 HP u16 @0x100A48, P2 HP u16 @0x100A4C, round timer u8 @0x100AC7
DEFAULT_ENTRIES = [(0x100A48, 2), (0x100A4C, 2), (0x100AC7, 0)]


class MameBridge:
    def __init__(self, *, instance: str = "bridge", entries=None,
                 ready_delay: int = 30, ready_timeout: int = 600,
                 windowed: bool = False, extra_args: list[str] | None = None,
                 profile: str | None = None, accept_timeout: float = 90.0):
        if profile:
            from profiles import resolve
            prof = resolve(profile)
            windowed = prof.windowed
            extra_args = list(prof.extra) + (extra_args or [])
        self.entries = list(entries if entries is not None else DEFAULT_ENTRIES)
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.bind(("127.0.0.1", 0))          # dynamic port: no TIME_WAIT traps
        self.port = self._srv.getsockname()[1]
        self._srv.listen(1)
        self._srv.settimeout(accept_timeout)

        self.proc = MameProcess(port=self.port, instance=instance,
                                windowed=windowed, extra_args=extra_args)
        self.proc.start()
        try:
            self.conn, _ = self._srv.accept()
        except OSError as e:
            self.proc.stop()
            raise BridgeError(
                f"MAME never connected within {accept_timeout}s "
                f"(boot failed?). log tail:\n{self.proc.tail_log()}") from e
        self.conn.settimeout(60.0)

        raw = recv_exact(self.conn, _HEADER.size)
        op, length = _HEADER.unpack(raw)
        hello = parse_hello(recv_exact(self.conn, length))
        if op != MSG_HELLO:
            raise BridgeError(f"expected HELLO, got opcode {op}")
        self.hello = hello

        payload = pack_config(0, 0, ready_delay, ready_timeout, self.entries)
        self.conn.sendall(payload)
        op2, _ = recv_msg(self.conn)
        if op2 != MSG_OK:
            raise BridgeError(f"CONFIG not acknowledged (opcode {op2})")

    # ---------------------------------------------------------------- helpers
    def _recv_state(self, n_pixels_expected: bool = False):
        """Returns (values tuple, frame|None) where frame=(w,h,rgb32bytes)."""
        op, payload = recv_msg(self.conn)
        if op != MSG_STATE:
            raise BridgeError(f"expected STATE, got opcode {op}")
        values = parse_state_values(payload, len(self.entries))
        off = 4 * len(self.entries)
        frame = None
        if off < len(payload):
            flag = payload[off]
            off += 1
            if flag == 1:
                w, h = struct.unpack_from("<HH", payload, off)
                off += 4
                data = payload[off:off + w * h * 4]
                frame = (w, h, data)
        return values, frame

    def _recv_state_values(self) -> tuple[int, ...]:
        return self._recv_state()[0]

    # ---------------------------------------------------------------- commands
    def action(self, dir_mask: int = 0, btn_mask: int = 0, press_frames: int = 2,
               step_frames: int = 1, want_pixels: bool = False):
        self.conn.sendall(pack_action(dir_mask, btn_mask, press_frames,
                                      step_frames, want_pixels))
        return self._recv_state()

    def press(self, role: int, mask: int, press_frames: int = 5,
              wait_frames: int = 30) -> tuple[int, ...]:
        self.conn.sendall(pack_press(role, mask, press_frames, wait_frames))
        return self._recv_state_values()

    def readf(self, role: int = 0) -> dict[int, int]:
        """Mechanical input echo: {mask: value} for the role's ioport fields."""
        self.conn.sendall(pack_readf(role))
        op, payload = recv_msg(self.conn)
        if op != MSG_STATE:
            raise BridgeError(f"expected STATE for READF, got opcode {op}")
        (count,) = struct.unpack("<B", payload[:1])
        out: dict[int, int] = {}
        off = 1
        for _ in range(count):
            out[payload[off]] = payload[off + 1]
            off += 2
        return out

    def readf_field(self, mask: int, role: int = 0) -> int:
        """field:value() readback for one mask (diagnostic)."""
        self.conn.sendall(pack_readf(role, mask))
        op, payload = recv_msg(self.conn)
        if op != MSG_STATE:
            raise BridgeError(f"expected STATE for READF, got opcode {op}")
        return payload[2] if len(payload) >= 3 else -1

    def write(self, addr: int, type_code: int, value: int) -> None:
        self.conn.sendall(pack_write(addr, type_code, value))
        op, _ = recv_msg(self.conn)
        if op != MSG_OK:
            raise BridgeError(f"WRITE not acknowledged (opcode {op})")

    def set(self, key: str, value: str) -> None:
        self.conn.sendall(pack_set(key, value))
        op, _ = recv_msg(self.conn)
        if op != MSG_OK:
            raise BridgeError(f"SET not acknowledged (opcode {op})")

    def save_state(self, name: str) -> None:
        self.conn.sendall(pack_save_state(name))
        op, _ = recv_msg(self.conn)
        if op != MSG_OK:
            raise BridgeError(f"SAVE_STATE failed (opcode {op})")

    def read_mem(self, addr: int, type_code: int = 4) -> int:
        """OP_READ: dynamic single-point read for uid-relative entity reads a
        static CONFIG table cannot express. Reply is a 1-value STATE frame
        (<I4 value><B pixels-flag=0>). Type codes match the CONFIG readers:
        0=u8 1=i8 2=u16 3=i16 4=u32."""
        self.conn.sendall(pack_read(addr, type_code))
        op, payload = recv_msg(self.conn)
        if op != MSG_STATE:
            raise BridgeError(f"expected STATE for READ, got opcode {op}")
        (value,) = struct.unpack_from("<I", payload, 0)
        return value

    def load_state(self, name: str) -> tuple[int, ...]:
        self.conn.sendall(pack_load_state(name))
        op, payload = recv_msg(self.conn)
        if op != MSG_READY:
            raise BridgeError(f"expected READY after load, got opcode {op}")
        return parse_state_values(payload, len(self.entries))

    def ping(self) -> float:
        t0 = time.perf_counter()
        self.conn.sendall(pack_msg(OP_PING))
        op, _ = recv_msg(self.conn)
        if op != MSG_PONG:
            raise BridgeError(f"expected PONG, got opcode {op}")
        return time.perf_counter() - t0

    def quit(self, timeout: float = 10.0) -> int | None:
        try:
            self.conn.sendall(pack_msg(OP_QUIT))
        except OSError:
            pass
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc.proc.poll() is not None:
                return self.proc.proc.returncode
            time.sleep(0.2)
        return None

    def close(self) -> None:
        for s in (self.conn, self._srv):
            try:
                s.close()
            except OSError:
                pass
        self.proc.stop()


def ensure_instance_states(instance: str) -> None:
    """Ensure state/samsho2 directory in data/mame/instance/<instance> contains
    necessary savestates and r1.sta from the canonical rl directory."""
    if instance == "rl":
        return
    dst_dir = Path(PROJECT) / "data" / "mame" / "instance" / instance / "state" / "samsho2"
    dst_dir.mkdir(parents=True, exist_ok=True)
    src_dir = Path(PROJECT) / "data" / "mame" / "instance" / "rl" / "state" / "samsho2"
    if not src_dir.exists():
        src_dir = Path(PROJECT) / "data" / "mame" / "instance" / "rl_ag_smoke" / "state" / "samsho2"
    if not src_dir.exists():
        return
    import shutil
    for sta in src_dir.glob("*.sta"):
        target = dst_dir / sta.name
        if not target.exists() or target.stat().st_size != sta.stat().st_size:
            shutil.copy2(sta, target)


class BridgeSession:
    """Watchdog wrapper: owns a bridge; every operation runs in a worker
    thread with a timeout. A hung lockstep (Lua/Python deadlock) is recovered
    by abandoning the worker, killing MAME (unblocks its socket), rebuilding,
    and re-anchoring. Threads leaked by hangs die when mame is killed.
    """

    def __init__(self, *, mode: str = "1p", instance: str = "bot",
                 entries=None, windowed: bool = False,
                 extra_args: list[str] | None = None):
        self.mode = mode
        self.instance = instance
        self.windowed = windowed
        self.extra_args = list(extra_args) if extra_args else []
        if entries is None:
            # full-WRAM layout is assumed by nav HP checks, the state parser
            # and the gym env — make it the default, not the caller's job
            from diff_scan import build_wram_dump_entries
            entries = build_wram_dump_entries()
        self.entries = entries
        self.bridge: MameBridge | None = None
        self.resets = 0
        self._leaked: list = []

    def _run(self, fn, timeout: float):
        """Run fn() in a thread; on hang raise BridgeError after timeout."""
        import threading as _th
        box: dict = {}

        def worker():
            try:
                box["result"] = fn()
                box["ok"] = True
            except Exception as e:  # noqa: BLE001
                box["error"] = e
                box["ok"] = False

        w = _th.Thread(target=worker, daemon=True)
        w.start()
        w.join(timeout=timeout)
        if w.is_alive():
            self._kill()
            raise BridgeError(f"operation hung >{timeout:.0f}s (worker abandoned)")
        if box.get("ok"):
            return box["result"]
        raise box.get("error", BridgeError("worker failed"))

    def _kill(self) -> None:
        if self.bridge is not None:
            try:
                self.bridge.proc.proc.kill()
            except Exception:  # noqa: BLE001
                pass
            try:
                self.bridge.close()
            except Exception:  # noqa: BLE001
                pass
            self._leaked.append(self.bridge)
            self.bridge = None

    def _rebuild(self) -> None:
        # late imports: mame_nav chains back to mame_client (avoid cycle)
        from mame_nav import ensure_active_round, reach_round1_anchor
        import time as _t
        if self.bridge is not None:
            self._kill()
        _t.sleep(1.0)
        # FIXED instance name: the verified "r1" savestate persists in this
        # instance's state dir, so rebuilds after a hang reuse it instead of
        # re-navigating (2026-11-06 user runs: -rN suffix made every rebuild
        # re-nav, and missed freeze windows descended into the attract-demo
        # verification loop -> all three daytime sessions died unanchored).
        ensure_instance_states(self.instance)
        self.bridge = MameBridge(instance=self.instance, entries=self.entries,
                                 windowed=self.windowed, extra_args=self.extra_args)
        # fast path: load + burn the persisted anchor (~15s, no navigation).
        # machine:load on a MISSING file silently "succeeds" (Lua pcall sees
        # no error) and we would burn frames reading attract-mode HP — check
        # the file exists first.
        state_file = (Path(PROJECT) / "data" / "mame" / "instance"
                      / self.instance / "state" / "samsho2" / "r1.sta")
        if not state_file.exists():
            print("[BridgeSession] no persisted anchor; navigating", flush=True)
        else:
            try:
                ok, hp1, _hp2, _t2 = self._run(
                    lambda: ensure_active_round(self.bridge), 90.0)
                if ok and hp1 == 0x80:
                    return
                print(f"[BridgeSession] anchor fast path unusable "
                      f"(ok={ok} hp1={hp1:#x}); falling back to navigation",
                      flush=True)
            except BridgeError as e:
                print(f"[BridgeSession] fast path failed ({e}); navigating",
                      flush=True)
        ok = False
        for attempt in range(3):
            r = self._run(lambda: reach_round1_anchor(self.bridge,
                                                      mode=self.mode), 900.0)
            ok = r[0]
            if ok:
                break
            print(f"[BridgeSession] anchor attempt {attempt} failed; reset",
                  flush=True)
            self._kill()
            _t2 = __import__("time")
            _t2.sleep(1.0)
            self.bridge = MameBridge(instance=self.instance,
                                     entries=self.entries,
                                     windowed=self.windowed,
                                     extra_args=self.extra_args)
        if not ok:
            raise BridgeError("re-anchor failed after 3 attempts")
        self._run(lambda: ensure_active_round(self.bridge), 60.0)

    def start(self) -> None:
        self._rebuild()

    def call(self, method: str, *args, timeout: float = 30.0, **kwargs):
        for attempt in range(2):
            try:
                if self.bridge is None:
                    self._rebuild()
                return self._run(
                    lambda: getattr(self.bridge, method)(*args, **kwargs),
                    timeout)
            except BridgeError as e:
                if "hung" in str(e) and attempt == 0:
                    _t = None
                    import time as _t2
                    _t2.sleep(1.0)
                    self._rebuild()
                    continue
                raise

    def ensure_active(self, timeout: float = 120.0, state_name: str = "r1",
                      settle_frames: int = 300, skip_scenes: bool = False):
        """load persisted anchor -> burn the freeze -> (ok, hp1, hp2, timer)."""
        from mame_nav import ensure_active_round
        if self.bridge is None:
            self._rebuild()
        return self._run(lambda: ensure_active_round(
            self.bridge, state_name=state_name, settle_frames=settle_frames,
            skip_scenes=skip_scenes), timeout)
