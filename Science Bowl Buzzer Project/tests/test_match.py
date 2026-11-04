from __future__ import annotations

import sqlite3

from science_bowl_buzzer.match import MatchController
from science_bowl_buzzer.storage import Database


class FakeScoreDisplay:
    def __init__(self) -> None:
        self.values: list[tuple[int, int]] = []

    def show_scores(self, team_a: int, team_b: int) -> None:
        self.values.append((team_a, team_b))


class FakeResetOutput:
    available = True

    def __init__(self) -> None:
        self.pulses = 0

    def pulse(self) -> None:
        self.pulses += 1


def test_wrong_attempt_keeps_same_question(tmp_path):
    reset = FakeResetOutput()
    db = Database(tmp_path / "test.db")
    controller = MatchController(db, reset_output=reset)

    controller.buzz(1)
    assert controller.snapshot()["pending"]["interrupt"] is True
    controller.wrong()
    state = controller.snapshot()

    assert state["question"]["question_number"] == 1
    assert state["attempts"][0]["player_id"] == 1
    assert state["attempts"][0]["result"] == "Wrong"
    assert state["attempts"][0]["interrupt"] is True
    assert state["attempts"][0]["correct"] is False
    assert state["timer"]["running"] is False
    assert reset.pulses == 1


def test_correct_finalizes_and_advances_question(tmp_path):
    reset = FakeResetOutput()
    db = Database(tmp_path / "test.db")
    controller = MatchController(db, reset_output=reset)

    controller.buzz(9)
    controller.correct()
    state = controller.snapshot()

    assert state["question"]["question_number"] == 2
    exported = db.export_csv(tmp_path / "round.csv")
    text = exported.read_text(encoding="utf-8")
    assert "Correct" in text
    assert "9,Correct,true,true" in text
    assert reset.pulses == 1


def test_timed_correct_is_not_an_interrupt(tmp_path):
    reset = FakeResetOutput()
    db = Database(tmp_path / "timed-correct.db")
    controller = MatchController(db, reset_output=reset)

    controller.start_timer()
    controller.buzz(9)
    assert controller.snapshot()["pending"]["interrupt"] is False
    controller.correct()

    assert controller.snapshot()["question"]["question_number"] == 2
    text = db.export_csv(tmp_path / "timed-correct.csv").read_text(encoding="utf-8")
    assert "9,Correct,false,true" in text
    assert reset.pulses == 1


def test_timed_incorrect_restarts_timer(tmp_path):
    reset = FakeResetOutput()
    db = Database(tmp_path / "timed-incorrect.db")
    controller = MatchController(db, reset_output=reset)

    controller.start_timer()
    controller.buzz(2)
    controller.wrong()
    state = controller.snapshot()

    assert state["question"]["question_number"] == 1
    assert state["attempts"][0]["interrupt"] is False
    assert state["attempts"][0]["correct"] is False
    assert state["timer"]["running"] is True
    assert state["timer"]["remaining_ms"] > 4900
    assert reset.pulses == 1
    controller.time_up()
    text = db.export_csv(tmp_path / "timed-incorrect.csv").read_text(encoding="utf-8")
    assert "2,Wrong,false,false" in text
    assert reset.pulses == 2


def test_time_up_creates_blank_attempt(tmp_path):
    reset = FakeResetOutput()
    db = Database(tmp_path / "test.db")
    controller = MatchController(db, reset_output=reset)

    controller.start_timer()
    controller.time_up()
    state = controller.snapshot()

    assert state["question"]["question_number"] == 2
    text = db.export_csv(tmp_path / "round.csv").read_text(encoding="utf-8")
    assert "Time Up" in text
    assert "Blank" in text
    assert reset.pulses == 1


def test_delete_clears_pending_and_resets_buzzers(tmp_path):
    reset = FakeResetOutput()
    controller = MatchController(
        Database(tmp_path / "delete.db"),
        reset_output=reset,
    )

    controller.buzz(5)
    result = controller.delete()
    state = controller.snapshot()

    assert result == {"accepted": True, "deleted": "pending"}
    assert state["pending"] is None
    assert state["attempts"] == []
    assert state["timer"]["running"] is False
    assert reset.pulses == 1


def test_existing_database_adds_attempt_flags(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            attempt_order INTEGER NOT NULL,
            player_id INTEGER,
            team TEXT,
            elapsed_ms INTEGER,
            result TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO attempts
            (question_id, attempt_order, player_id, team, elapsed_ms, result, created_at)
        VALUES (1, 1, 4, 'A', 1200, 'Correct', '2026-01-01T00:00:00+00:00')
        """
    )
    conn.commit()
    conn.close()

    db = Database(path)
    try:
        attempt = db.attempts_for_question(1)[0]
        assert attempt.interrupt is None
        assert attempt.correct is True
    finally:
        db.close()


def test_score_buttons_are_manual(tmp_path):
    db = Database(tmp_path / "test.db")
    controller = MatchController(db)

    controller.add_score("A", 4, "Toss-up")
    controller.add_score("B", 10, "Bonus")
    state = controller.snapshot()

    assert state["scores"] == {"A": 4, "B": 10}


def test_manual_score_updates_physical_display(tmp_path):
    display = FakeScoreDisplay()
    controller = MatchController(Database(tmp_path / "buzzer.db"), score_display=display)

    controller.add_score("A", 4, "Toss-up")
    controller.add_score("B", 10, "Bonus")

    assert display.values == [(0, 0), (4, 0), (4, 10)]


def test_manual_reset_mode_requires_physical_button(tmp_path):
    controller = MatchController(Database(tmp_path / "manual-reset.db"))

    result = controller.reset_buzzers()

    assert result["accepted"] is False
    assert result["manual_reset_required"] is True
    assert controller.snapshot()["reset"] == {
        "available": False,
        "mode": "manual",
    }


def test_automatic_reset_mode_pulses_output(tmp_path):
    reset = FakeResetOutput()
    controller = MatchController(
        Database(tmp_path / "automatic-reset.db"),
        reset_output=reset,
    )

    result = controller.reset_buzzers()

    assert result == {"accepted": True, "manual_reset_required": False}
    assert reset.pulses == 1
    assert controller.snapshot()["reset"]["mode"] == "automatic"
