"""Demo logger for Samurai Shodown II live spectating matches."""
from __future__ import annotations

import datetime
from pathlib import Path


class DemoLogger:
    def __init__(
        self,
        log_dir: str | Path,
        p1_name: str = "haohmaru",
        p2_name: str = "earthquake",
        mode: str = "single",
        speed: float = 1.0,
    ):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.p1_name = p1_name.lower()
        self.p2_name = p2_name.lower()
        self.mode = mode
        self.speed = speed
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        self.running_filename = f"{self.timestamp}_{self.p1_name}_vs_{self.p2_name}_RUNNING.log"
        self.active_path = self.log_dir / self.running_filename

        self._file = open(self.active_path, "w", encoding="utf-8")
        self._write_header()

    def _write_header(self):
        self._file.write("=" * 72 + "\n")
        self._file.write("     SAMURAI SHODOWN II - LIVE MATCH DEMO LOG\n")
        self._file.write("=" * 72 + "\n")
        self._file.write(f"  Match Date / Time : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self._file.write(f"  Player 1 (Agent)  : {self.p1_name.upper()}\n")
        self._file.write(f"  Player 2 (Opponent: {self.p2_name.upper()}\n")
        self._file.write(f"  Match Mode        : {'Best-of-3 (BO3)' if self.mode == 'bo3' else 'Single Round KO'}\n")
        self._file.write(f"  Emulation Speed   : {self.speed}x\n")
        self._file.write("=" * 72 + "\n\n")
        self._file.write(f"{'Step/Frame':<12} | {'Round':<5} | {'Action Performed':<22} | {'P1 HP':<16} | {'P2 HP':<16}\n")
        self._file.write("-" * 80 + "\n")
        self._file.flush()

    def log_step(
        self,
        step: int,
        act_id: int,
        act_name: str,
        p1_hp: int,
        p2_hp: int,
        round_no: int = 1,
    ):
        p1_pct = max(0.0, p1_hp / 128.0) * 100
        p2_pct = max(0.0, p2_hp / 164.0) * 100
        act_str = f"{act_id} ({act_name})"
        p1_str = f"{p1_hp:03d}/128 ({p1_pct:5.1f}%)"
        p2_str = f"{p2_hp:03d}/164 ({p2_pct:5.1f}%)"
        line = f"Step {step:05d}   | R{round_no:<4} | {act_str:<22} | P1: {p1_str:<12} | P2: {p2_str:<12}\n"
        self._file.write(line)
        if step % 20 == 0:
            self._file.flush()

    def log_round(
        self,
        round_no: int,
        winner: str,
        score: tuple[int, int],
        steps: int,
    ):
        self._file.write("\n" + "-" * 72 + "\n")
        self._file.write(f"  >>> ROUND {round_no} FINISHED! <<<\n")
        self._file.write(f"  Round Winner : {winner.upper()}\n")
        self._file.write(f"  Current Score: P1 {score[0]} - {score[1]} P2\n")
        self._file.write(f"  Round Steps  : {steps} steps\n")
        self._file.write("-" * 72 + "\n\n")
        self._file.flush()

    def finish(
        self,
        final_winner: str,
        score: tuple[int, int],
        total_steps: int,
    ) -> Path:
        is_p1_win = (final_winner.lower() == self.p1_name.lower())
        tag = "VICTORY" if is_p1_win else "DEFEAT"
        final_filename = f"{self.timestamp}_{self.p1_name}_vs_{self.p2_name}_{tag}.log"
        final_path = self.log_dir / final_filename

        self._file.write("\n" + "=" * 72 + "\n")
        self._file.write(f"             ★ ★ ★  MATCH RESULT: {tag} ({score[0]}-{score[1]})  ★ ★ ★\n")
        self._file.write(f"  Final Winner : {final_winner.upper()}\n")
        self._file.write(f"  Final Score  : P1 {score[0]} - {score[1]} P2\n")
        self._file.write(f"  Total Steps  : {total_steps} steps\n")
        self._file.write("=" * 72 + "\n")
        self._file.flush()
        self._file.close()

        # Rename file
        if self.active_path.exists():
            self.active_path.rename(final_path)

        return final_path
