from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .hardware import NoopResetOutput, ResetOutput
from .score_display import NoopScoreDisplay, ScoreDisplay
from .storage import Database


PLAYER_TEAMS = {
    1: "A",
    2: "A",
    3: "A",
    4: "A",
    5: "A",
    6: "A",
    7: "A",
    8: "A",
    9: "B",
    10: "B",
    11: "B",
    12: "B",
    13: "B",
    14: "B",
    15: "B",
    16: "B",
}


@dataclass
class PendingWinner:
    player_id: int
    team: str
    elapsed_ms: int
    interrupt: bool
    person_id: str | None = None
    player_name: str | None = None


@dataclass
class TimerState:
    duration_ms: int = 5000
    started_monotonic: float | None = None

    @property
    def running(self) -> bool:
        return self.started_monotonic is not None

    def start(self, duration_ms: int = 5000) -> None:
        self.duration_ms = duration_ms
        self.started_monotonic = time.monotonic()

    def stop(self) -> None:
        self.started_monotonic = None

    def remaining_ms(self) -> int:
        if self.started_monotonic is None:
            return self.duration_ms
        elapsed = int((time.monotonic() - self.started_monotonic) * 1000)
        return max(0, self.duration_ms - elapsed)

    def expired(self) -> bool:
        return self.running and self.remaining_ms() <= 0


class MatchController:
    def __init__(
        self,
        db: Database,
        reset_output: ResetOutput | None = None,
        score_display: ScoreDisplay | None = None,
    ) -> None:
        self.db = db
        self.reset_output = reset_output or NoopResetOutput()
        self.reset_available = bool(getattr(self.reset_output, "available", True))
        self.score_display = score_display or NoopScoreDisplay()
        self.pending: PendingWinner | None = None
        self.timer = TimerState()
        self.question_started = time.monotonic()
        self._refresh_score_display()

    def _refresh_score_display(self) -> None:
        scores = self.db.state_snapshot()["scores"]
        self.score_display.show_scores(int(scores["A"]), int(scores["B"]))

    def _elapsed_ms(self) -> int:
        return int((time.monotonic() - self.question_started) * 1000)

    def _reset_buzzers(self) -> bool:
        if not self.reset_available:
            return False
        self.reset_output.pulse()
        return True

    def buzz(self, player_id: int) -> dict[str, Any]:
        self._expire_timer_if_needed()
        if player_id < 1 or player_id > 16:
            raise ValueError("player_id must be 1..16")
        if self.pending is not None:
            return {"accepted": False, "reason": "winner already pending"}
        interrupt = not self.timer.running
        self.timer.stop()
        team = PLAYER_TEAMS.get(player_id, "?")
        person_id, player_name = self.db.player_identity(player_id)
        self.pending = PendingWinner(
            player_id=player_id,
            team=team,
            elapsed_ms=self._elapsed_ms(),
            interrupt=interrupt,
            person_id=person_id,
            player_name=player_name,
        )
        return {"accepted": True, "player_id": player_id, "team": team}

    def correct(self) -> dict[str, Any]:
        self._expire_timer_if_needed()
        if self.pending is None:
            return {"accepted": False, "reason": "no pending winner"}
        pending = self.pending
        self.db.add_attempt(
            pending.player_id,
            pending.team,
            pending.elapsed_ms,
            "Correct",
            interrupt=pending.interrupt,
            correct=True,
            person_id=pending.person_id,
            player_name=pending.player_name,
        )
        self.db.finalize_current_question("Correct")
        self.pending = None
        self.timer.stop()
        self.question_started = time.monotonic()
        self._reset_buzzers()
        return {"accepted": True}

    def wrong(self) -> dict[str, Any]:
        self._expire_timer_if_needed()
        if self.pending is None:
            return {"accepted": False, "reason": "no pending winner"}
        pending = self.pending
        self.db.add_attempt(
            pending.player_id,
            pending.team,
            pending.elapsed_ms,
            "Wrong",
            interrupt=pending.interrupt,
            correct=False,
            person_id=pending.person_id,
            player_name=pending.player_name,
        )
        self.pending = None
        self._reset_buzzers()
        attempts = self.db.attempts_for_question(self.db.current_question()["id"])
        if sum(attempt.result == "Wrong" for attempt in attempts) >= 2:
            self.db.finalize_current_question("Wrong")
            self.timer.stop()
            self.question_started = time.monotonic()
        elif not pending.interrupt:
            self.timer.start()
        return {"accepted": True}

    def delete(self) -> dict[str, Any]:
        if self.pending is not None:
            self.pending = None
            self.timer.stop()
            self._reset_buzzers()
            return {"accepted": True, "deleted": "pending"}
        deleted = self.db.delete_last_unfinalized_attempt()
        self.timer.stop()
        self._reset_buzzers()
        return {"accepted": deleted, "deleted": "last_attempt" if deleted else None}

    def start_timer(self) -> dict[str, Any]:
        self._expire_timer_if_needed()
        if self.pending is not None:
            return {"accepted": False, "reason": "clear pending winner first"}
        self.timer.start()
        return {"accepted": True}

    def undo(self) -> dict[str, Any]:
        # Do not expire a running timer and accidentally create an extra record.
        self.timer.stop()
        if self.pending is not None:
            self.pending = None
            result = {"accepted": True, "deleted": "pending"}
        else:
            result = self.db.undo_last_attempt()
        self.question_started = time.monotonic()
        self._reset_buzzers()
        return result

    def load_round(self, round_id: int) -> dict[str, Any]:
        if self.pending is not None or self.timer.running:
            raise ValueError("Finish or delete the pending buzz and stop the timer before loading another game")
        self.db.load_round(round_id)
        self.question_started = time.monotonic()
        self._refresh_score_display()
        self._reset_buzzers()
        return {"accepted": True}

    def time_up(self) -> dict[str, Any]:
        if self.pending is not None:
            return {"accepted": False, "reason": "clear pending winner first"}
        self.db.add_attempt(
            None,
            None,
            self._elapsed_ms(),
            "Blank",
            interrupt=None,
            correct=None,
        )
        self.db.finalize_current_question("Time Up")
        self.timer.stop()
        self.question_started = time.monotonic()
        self._reset_buzzers()
        return {"accepted": True}

    def add_score(self, team: str, points: int, reason: str) -> dict[str, Any]:
        if team not in {"A", "B"}:
            raise ValueError("team must be A or B")
        self.db.add_score(team, points, reason)
        self._refresh_score_display()
        return {"accepted": True}

    def new_round(self, name: str | None = None) -> dict[str, Any]:
        self.db.new_round(name)
        self._refresh_score_display()
        self.pending = None
        self.timer.stop()
        self.question_started = time.monotonic()
        self._reset_buzzers()
        return {"accepted": True}

    def reset_buzzers(self) -> dict[str, Any]:
        if not self._reset_buzzers():
            return {
                "accepted": False,
                "manual_reset_required": True,
                "reason": "Press the physical EC500 reset button",
            }
        return {"accepted": True, "manual_reset_required": False}

    def _expire_timer_if_needed(self) -> None:
        if self.timer.expired() and self.pending is None:
            self.time_up()

    def snapshot(self) -> dict[str, Any]:
        self._expire_timer_if_needed()
        state = self.db.state_snapshot()
        state["pending"] = None if self.pending is None else self.pending.__dict__
        state["timer"] = {
            "running": self.timer.running,
            "remaining_ms": self.timer.remaining_ms(),
            "duration_ms": self.timer.duration_ms,
        }
        state["reset"] = {
            "available": self.reset_available,
            "mode": "automatic" if self.reset_available else "manual",
        }
        return state
