from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from science_bowl_buzzer.hardware import WinnerInputPoller
from science_bowl_buzzer.keypad import KeypadCommand, command_for_key_code
from science_bowl_buzzer.match import MatchController
from science_bowl_buzzer.score_display import MAX7219ScoreDisplay
from science_bowl_buzzer.server import HardwareRuntime
from science_bowl_buzzer.storage import Database
from science_bowl_buzzer.subject_infer import infer_subjects_from_text


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


class FakeInputSource:
    def __init__(self) -> None:
        self.active: list[int] = []

    def read_active_players(self) -> list[int]:
        return list(self.active)


class FakeKeypad:
    def __init__(self, commands: list[KeypadCommand]) -> None:
        self.commands = commands

    def read_commands(self) -> list[KeypadCommand]:
        commands, self.commands = self.commands, []
        return commands


def make_db(tmp: Path) -> Database:
    return Database(tmp / "test.db")


def test_wrong_attempt_keeps_same_question(tmp: Path) -> None:
    db = make_db(tmp)
    try:
        reset = FakeResetOutput()
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
    finally:
        db.close()


def test_correct_finalizes_and_advances_question(tmp: Path) -> None:
    db = make_db(tmp)
    try:
        reset = FakeResetOutput()
        controller = MatchController(db, reset_output=reset)
        controller.buzz(9)
        controller.correct()
        state = controller.snapshot()
        assert state["question"]["question_number"] == 2
        text = db.export_csv(tmp / "round.csv").read_text(encoding="utf-8")
        assert "Correct" in text
        assert "9,Correct,true,true" in text
        assert reset.pulses == 1
    finally:
        db.close()


def test_timed_correct_is_not_an_interrupt(tmp: Path) -> None:
    db = make_db(tmp)
    try:
        reset = FakeResetOutput()
        controller = MatchController(db, reset_output=reset)
        controller.start_timer()
        controller.buzz(9)
        assert controller.snapshot()["pending"]["interrupt"] is False
        controller.correct()
        assert controller.snapshot()["question"]["question_number"] == 2
        text = db.export_csv(tmp / "round.csv").read_text(encoding="utf-8")
        assert "9,Correct,false,true" in text
        assert reset.pulses == 1
    finally:
        db.close()


def test_timed_incorrect_restarts_timer(tmp: Path) -> None:
    db = make_db(tmp)
    try:
        reset = FakeResetOutput()
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
        text = db.export_csv(tmp / "round.csv").read_text(encoding="utf-8")
        assert "2,Wrong,false,false" in text
        assert reset.pulses == 2
    finally:
        db.close()


def test_time_up_creates_blank_attempt(tmp: Path) -> None:
    db = make_db(tmp)
    try:
        reset = FakeResetOutput()
        controller = MatchController(db, reset_output=reset)
        controller.start_timer()
        controller.time_up()
        state = controller.snapshot()
        assert state["question"]["question_number"] == 2
        text = db.export_csv(tmp / "round.csv").read_text(encoding="utf-8")
        assert "Time Up" in text
        assert "Blank" in text
        assert reset.pulses == 1
    finally:
        db.close()


def test_delete_clears_pending_and_resets_buzzers(tmp: Path) -> None:
    db = make_db(tmp)
    try:
        reset = FakeResetOutput()
        controller = MatchController(db, reset_output=reset)
        controller.buzz(5)
        result = controller.delete()
        state = controller.snapshot()
        assert result == {"accepted": True, "deleted": "pending"}
        assert state["pending"] is None
        assert state["attempts"] == []
        assert state["timer"]["running"] is False
        assert reset.pulses == 1
    finally:
        db.close()


def test_existing_database_adds_attempt_flags(tmp: Path) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    path = tmp / "legacy.db"
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


def test_score_buttons_are_manual(tmp: Path) -> None:
    db = make_db(tmp)
    try:
        controller = MatchController(db)
        controller.add_score("A", 4, "Toss-up")
        controller.add_score("B", 10, "Bonus")
        state = controller.snapshot()
        assert state["scores"] == {"A": 4, "B": 10}
    finally:
        db.close()


def test_manual_score_updates_physical_display(tmp: Path) -> None:
    db = make_db(tmp)
    try:
        display = FakeScoreDisplay()
        controller = MatchController(db, score_display=display)
        controller.add_score("A", 4, "Toss-up")
        controller.add_score("B", 10, "Bonus")
        assert display.values == [(0, 0), (4, 0), (4, 10)]
    finally:
        db.close()


def test_manual_reset_mode_requires_physical_button(tmp: Path) -> None:
    db = make_db(tmp)
    try:
        controller = MatchController(db)
        result = controller.reset_buzzers()
        assert result["accepted"] is False
        assert result["manual_reset_required"] is True
        assert controller.snapshot()["reset"] == {
            "available": False,
            "mode": "manual",
        }
    finally:
        db.close()


def test_automatic_reset_mode_pulses_output(tmp: Path) -> None:
    db = make_db(tmp)
    try:
        reset = FakeResetOutput()
        controller = MatchController(db, reset_output=reset)
        result = controller.reset_buzzers()
        assert result == {"accepted": True, "manual_reset_required": False}
        assert reset.pulses == 1
        assert controller.snapshot()["reset"]["mode"] == "automatic"
    finally:
        db.close()


def test_winner_poller_debounces_and_rearms(tmp: Path) -> None:
    source = FakeInputSource()
    winners: list[int] = []
    poller = WinnerInputPoller(source, winners.append, stable_reads=2)
    poller.poll()
    source.active = [4]
    poller.poll()
    poller.poll()
    poller.poll()
    assert winners == [4]
    source.active = []
    poller.poll()
    source.active = [9]
    poller.poll()
    poller.poll()
    assert winners == [4, 9]


def test_winner_poller_rejects_multiple_lines(tmp: Path) -> None:
    source = FakeInputSource()
    winners: list[int] = []
    poller = WinnerInputPoller(source, winners.append, stable_reads=1)
    poller.poll()
    source.active = [2, 7]
    poller.poll()
    assert winners == []
    assert poller.last_error == "Multiple winner inputs are active: 2, 7"
    source.active = [2]
    poller.poll()
    assert winners == []
    source.active = []
    poller.poll()
    source.active = [2]
    poller.poll()
    assert winners == [2]


def test_winner_poller_requires_clear_after_startup(tmp: Path) -> None:
    source = FakeInputSource()
    source.active = [6]
    winners: list[int] = []
    poller = WinnerInputPoller(source, winners.append, stable_reads=1)
    poller.poll()
    assert winners == []
    source.active = []
    poller.poll()
    source.active = [6]
    poller.poll()
    assert winners == [6]


def test_numeric_keypad_mapping(tmp: Path) -> None:
    assert command_for_key_code("KEY_KP1") == KeypadCommand("correct")
    assert command_for_key_code("KEY_KP8") == KeypadCommand(
        "score", "B", 10, "Bonus"
    )
    assert command_for_key_code("KEY_KP6") is None


def test_hardware_runtime_dispatches_keypad(tmp: Path) -> None:
    db = make_db(tmp)
    try:
        controller = MatchController(db)
        runtime = HardwareRuntime(
            controller,
            keypad_source=FakeKeypad(
                [KeypadCommand("score", "A", 4, "Toss-up")]
            ),
        )
        runtime.poll()
        assert controller.snapshot()["scores"] == {"A": 4, "B": 0}
    finally:
        db.close()


def test_score_display_blanks_leading_zeroes(tmp: Path) -> None:
    digits = MAX7219ScoreDisplay._digits(4, 0x77)
    assert digits == [0x77, 0, 0, 0, 0, 0, 0, 0x66]


def test_infer_subjects_from_science_bowl_headers() -> None:
    text = """
    TOSS-UP
    1) BIOLOGY Short Answer
    This is a question.

    BONUS
    1) BIOLOGY Multiple Choice
    Bonus text.

    TOSS-UP
    2) EARTH AND SPACE SCIENCE Multiple Choice
    More text.
    """
    subjects = infer_subjects_from_text(text)
    assert subjects[1] == "Biology"
    assert subjects[2] == "Earth And Space Science"
    assert len(subjects) == 2


def main() -> None:
    tests = [
        test_wrong_attempt_keeps_same_question,
        test_correct_finalizes_and_advances_question,
        test_timed_correct_is_not_an_interrupt,
        test_timed_incorrect_restarts_timer,
        test_time_up_creates_blank_attempt,
        test_delete_clears_pending_and_resets_buzzers,
        test_existing_database_adds_attempt_flags,
        test_score_buttons_are_manual,
        test_manual_score_updates_physical_display,
        test_manual_reset_mode_requires_physical_button,
        test_automatic_reset_mode_pulses_output,
        test_winner_poller_debounces_and_rearms,
        test_winner_poller_rejects_multiple_lines,
        test_winner_poller_requires_clear_after_startup,
        test_numeric_keypad_mapping,
        test_hardware_runtime_dispatches_keypad,
        test_score_display_blanks_leading_zeroes,
    ]
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        for index, test in enumerate(tests):
            test(base / str(index))
            print(f"PASS {test.__name__}")
    test_infer_subjects_from_science_bowl_headers()
    print("PASS test_infer_subjects_from_science_bowl_headers")


if __name__ == "__main__":
    main()
