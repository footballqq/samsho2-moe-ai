"""Best-of-3 continuous match controller and state machine."""
from __future__ import annotations


class Bo3MatchController:
    """Manages continuous Best-of-3 match state machine across rounds.
    
    Guarantees:
    1. During round combat: lets policy act freely.
    2. During round transitions (KO animations, banners, refill): locks action to IDLE (0) or GUARD.
    3. On next round start: signals `round_just_started` so policies can reset their pointers.
    4. Terminates strictly when any fighter reaches 2 round wins.
    5. Anti-Flicker: requires sustained zero-streak (zs >= 3) to declare KO.
    6. Asymmetric Refill Aware: winner does not refill to 100% in SS2; tracks loser refill.
    7. Never awards false victory on intermission timeout.
    """

    def __init__(
        self,
        p1_name: str = "haohmaru",
        p2_name: str = "opponent",
        intermission_timeout: int = 700,
        intermission_action: int = 0,
    ):
        self.p1_name = p1_name.lower()
        self.p2_name = p2_name.lower()
        self.current_round = 1
        self.score = (0, 0)
        self.is_match_done = False
        self.is_in_round = True  # Armed
        self.round_just_started = True
        self.winner: str | None = None
        self.round_steps = 0
        self.intermission_steps = 0
        self.intermission_timeout = intermission_timeout
        self.intermission_action = intermission_action
        self.total_steps = 0
        self.round_winners: list[str] = []
        self._zero_streak = [0, 0]

    def update(
        self,
        p1_hp: int | float | None = None,
        p2_hp: int | float | None = None,
        tf: float | None = None,
        is_ratio: bool = False,
        p1_hp_ratio: float | None = None,
        p2_hp_ratio: float | None = None,
        rounds: tuple[int, int] | None = None,
    ) -> int | None:
        """Updates match state given current HP and/or HP ratios.
        
        Args:
            p1_hp: Player 1 memory HP (0..128)
            p2_hp: Player 2 memory HP (0..164)
            tf: Normalized timer value (optional)
            is_ratio: Whether p1_hp/p2_hp are 0..1.0 ratios
            p1_hp_ratio: Pixel bar ratio for P1 (0..1.0)
            p2_hp_ratio: Pixel bar ratio for P2 (0..1.0)
            rounds: Environment-level round wins/losses (optional)
            
        Returns:
            int: Action override (e.g. 0 for IDLE during intermission).
            None: No override, agent policy should act normally.
        """
        self.total_steps += 1
        if self.round_just_started:
            self.round_just_started = False

        if self.is_match_done:
            return 0

        # Determine alive status
        if is_ratio:
            p1_alive = (p1_hp or 0) > 0.01
            p2_alive = (p2_hp or 0) > 0.01
            r1_val = float(p1_hp or 0)
            r2_val = float(p2_hp or 0)
        else:
            p1_alive = (p1_hp is not None and p1_hp > 0) or (p1_hp_ratio is not None and p1_hp_ratio > 0.01)
            p2_alive = (p2_hp is not None and p2_hp > 0) or (p2_hp_ratio is not None and p2_hp_ratio > 0.01)
            r1_val = float(p1_hp_ratio if p1_hp_ratio is not None else ((p1_hp or 0) / 128.0))
            r2_val = float(p2_hp_ratio if p2_hp_ratio is not None else ((p2_hp or 0) / 164.0))

        # Track sustained zero-streak to eliminate single-frame hitstun or WRAM glitches
        zs1 = (self._zero_streak[0] + 1) if (not p1_alive) else 0
        zs2 = (self._zero_streak[1] + 1) if (not p2_alive) else 0
        self._zero_streak = [zs1, zs2]

        if self.is_in_round:
            self.round_steps += 1

            # Require at least 3 consecutive steps (6 frames = 100ms) of sustained death
            if zs2 >= 3 and p1_alive:
                # P1 wins this round
                p1_w, p2_w = self.score
                self.score = (p1_w + 1, p2_w)
                self.round_winners.append(self.p1_name)
                self.is_in_round = False
                self.intermission_steps = 0
                self._zero_streak = [0, 0]
                if self.score[0] >= 2:
                    self.is_match_done = True
                    self.winner = self.p1_name
                return self.intermission_action

            elif zs1 >= 3 and p2_alive:
                # P2 wins this round
                p1_w, p2_w = self.score
                self.score = (p1_w, p2_w + 1)
                self.round_winners.append(self.p2_name)
                self.is_in_round = False
                self.intermission_steps = 0
                self._zero_streak = [0, 0]
                if self.score[1] >= 2:
                    self.is_match_done = True
                    self.winner = self.p2_name
                return self.intermission_action

            elif zs1 >= 3 and zs2 >= 3:
                # Mutual KO (Draw)
                self.is_in_round = False
                self.intermission_steps = 0
                self._zero_streak = [0, 0]
                return self.intermission_action

            # Normal active combat
            return None

        else:
            # Currently in intermission / transition between rounds
            self.intermission_steps += 1

            if not self.is_match_done:
                # Minimum transition grace period (20 steps = 40 frames) to let KO animation clear
                if self.intermission_steps >= 20 and p1_alive and p2_alive:
                    # Next round is live if loser has refilled (> 0.50 bar or memory HP > 60)
                    last_winner = self.round_winners[-1] if self.round_winners else None
                    if last_winner == self.p1_name:
                        loser_refilled = (r2_val > 0.50 or (p2_hp or 0) > 60)
                    elif last_winner == self.p2_name:
                        loser_refilled = (r1_val > 0.50 or (p1_hp or 0) > 60)
                    else:
                        loser_refilled = (r1_val > 0.50 and r2_val > 0.50)

                    if loser_refilled:
                        self.current_round += 1
                        self.is_in_round = True
                        self.round_just_started = True
                        self.round_steps = 0
                        self.intermission_steps = 0
                        self._zero_streak = [0, 0]
                        return None  # Round begins!

            if self.intermission_steps >= self.intermission_timeout:
                self.is_match_done = True
                # Critical BUG fix: Never award false victory on intermission timeout!
                # If neither player legitimately reached 2 round wins, winner remains None.
                if self.score[0] >= 2:
                    self.winner = self.p1_name
                elif self.score[1] >= 2:
                    self.winner = self.p2_name
                else:
                    self.winner = None
                return 0

            return self.intermission_action
