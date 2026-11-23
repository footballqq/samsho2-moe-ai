"""MAME process lifecycle for the SS2 bridge: cmdline, spawn, watchdog, kill.

Ported from kof97_rl process.py with Windows adaptations:
  * dynamic port chosen by the caller (bind port 0), passed via MAME_SS2_SOCKET
  * Win32 Job Object instead of PR_SET_PDEATHSIG
  * per-instance cfg/nvram/state/snap dirs so instances never share global state
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from win32_process import assign_to_job, create_kill_on_close_job

PROJECT = Path(__file__).resolve().parent.parent


def resolve_mame_dir() -> Path:
    """Resolve MAME installation directory dynamically.
    1. Environment variable MAME_DIR
    2. Sibling directory: <parent>/mame0281b_x64
    3. Project subfolder: <project>/mame0281b_x64
    4. Fallback default: E:\\games\\mame0281b_x64
    """
    env_dir = os.environ.get("MAME_DIR")
    if env_dir:
        p = Path(env_dir)
        if (p / "mame.exe").exists():
            return p
    sibling = PROJECT.parent / "mame0281b_x64"
    if (sibling / "mame.exe").exists():
        return sibling
    sub = PROJECT / "mame0281b_x64"
    if (sub / "mame.exe").exists():
        return sub
    return Path(r"E:\games\mame0281b_x64")


MAME_DIR = resolve_mame_dir()
MAME_EXE = MAME_DIR / "mame.exe"
LOGS = PROJECT / "logs" / "mame"
INSTANCES = PROJECT / "data" / "mame" / "instance"
# env override for T5 watchpoint probe wrapper (default unchanged)
BRIDGE_LUA = PROJECT / "mame" / "bridge.lua"



class MameProcess:
    def __init__(self, *, port: int, instance: str = "bridge",
                 windowed: bool = False, extra_args: list[str] | None = None):
        self.port = port
        self.instance = instance
        self.windowed = windowed
        self.extra_args = extra_args or []
        self.proc: subprocess.Popen | None = None
        self.job = None
        inst = INSTANCES / instance
        self.inst_dir = inst
        self.log_path = LOGS / f"mame_{instance}_{int(time.time())}.log"

    def start(self) -> None:
        if not MAME_EXE.exists():
            raise FileNotFoundError(
                f"MAME executable not found at: {MAME_EXE}. "
                "Please set the MAME_DIR environment variable to your MAME installation directory "
                "(e.g. $env:MAME_DIR = 'C:\\mame0281b_x64') or place mame0281b_x64 beside this repo."
            )
        for sub in ("cfg", "nvram", "state", "snap"):
            (self.inst_dir / sub).mkdir(parents=True, exist_ok=True)
        LOGS.mkdir(parents=True, exist_ok=True)
        cmd = [
            str(MAME_EXE), "samsho2",
            "-autoboot_script",
            os.environ.get("MAME_BRIDGE_LUA", str(BRIDGE_LUA)),
            "-autoboot_delay", "1",
            "-skip_gameinfo",
            "-cfg_directory", str(self.inst_dir / "cfg"),
            "-nvram_directory", str(self.inst_dir / "nvram"),
            "-state_directory", str(self.inst_dir / "state"),
            "-snapshot_directory", str(self.inst_dir / "snap"),
        ]
        cmd += ["-window"] if self.windowed else ["-video", "none"]
        if not self.windowed:
            cmd += ["-sound", "none"]   # headless instances stay silent (0.281 syntax)
        cmd += self.extra_args

        env = dict(os.environ)
        env["MAME_SS2_SOCKET"] = f"127.0.0.1:{self.port}"
        log = self.log_path.open("wb")
        self.proc = subprocess.Popen(cmd, cwd=str(MAME_DIR), env=env,
                                     stdout=log, stderr=subprocess.STDOUT)
        self._log_handle = log
        self.job = create_kill_on_close_job()
        # best-effort: nested-job hosts may refuse; the 120s bridge timeout
        # still guarantees eventual cleanup
        assign_to_job(self.job, int(self.proc._handle))

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def tail_log(self, lines: int = 20) -> str:
        try:
            self._log_handle.flush()
            text = Path(self._log_handle.name).read_text(errors="replace")
            return "\n".join(text.splitlines()[-lines:])
        except OSError:
            return "<no log>"

    def stop(self, timeout: float = 5.0) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=timeout)
        try:
            self._log_handle.close()
        except OSError:
            pass
