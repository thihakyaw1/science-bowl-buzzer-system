from __future__ import annotations

import csv
import sqlite3
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Attempt:
    id: int
    question_id: int
    attempt_order: int
    player_id: int | None
    team: str | None
    elapsed_ms: int | None
    result: str
    interrupt: bool | None
    correct: bool | None
    created_at: str
    person_id: str | None = None
    player_name: str | None = None


class Database:
    def __init__(self, path: str | Path = "data/buzzer.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER NOT NULL,
                question_number INTEGER NOT NULL,
                subject TEXT,
                final_result TEXT,
                finalized_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(round_id) REFERENCES rounds(id)
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL,
                attempt_order INTEGER NOT NULL,
                player_id INTEGER,
                team TEXT,
                elapsed_ms INTEGER,
                result TEXT NOT NULL,
                interrupt INTEGER,
                correct INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(question_id) REFERENCES questions(id)
            );

            CREATE TABLE IF NOT EXISTS score_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER NOT NULL,
                team TEXT NOT NULL,
                points INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(round_id) REFERENCES rounds(id)
            );
            """
        )
        attempt_columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(attempts)").fetchall()
        }
        if "interrupt" not in attempt_columns:
            self.conn.execute("ALTER TABLE attempts ADD COLUMN interrupt INTEGER")
        if "correct" not in attempt_columns:
            self.conn.execute("ALTER TABLE attempts ADD COLUMN correct INTEGER")
        for column in ("person_id", "player_name"):
            if column not in attempt_columns:
                self.conn.execute(f"ALTER TABLE attempts ADD COLUMN {column} TEXT")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS round_subjects (
                round_id INTEGER NOT NULL, question_number INTEGER NOT NULL, subject TEXT NOT NULL,
                PRIMARY KEY(round_id, question_number));
        """)
        self.conn.execute("INSERT OR IGNORE INTO app_settings VALUES ('device_id', ?)",
                          (json.dumps(str(uuid.uuid4())),))
        self.conn.execute(
            """
            UPDATE attempts
            SET correct = CASE
                WHEN result = 'Correct' THEN 1
                WHEN result = 'Wrong' THEN 0
                ELSE NULL
            END
            WHERE correct IS NULL
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def active_round(self) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM rounds WHERE active = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            return row
        return self.new_round()

    def new_round(self, name: str | None = None) -> sqlite3.Row:
        self.conn.execute("UPDATE rounds SET active = 0 WHERE active = 1")
        created_at = utc_now()
        round_name = name or f"Round {created_at}"
        cur = self.conn.execute(
            "INSERT INTO rounds (name, created_at, active) VALUES (?, ?, 1)",
            (round_name, created_at),
        )
        round_id = cur.lastrowid
        self.conn.execute(
            """
            INSERT INTO questions (round_id, question_number, created_at)
            VALUES (?, 1, ?)
            """,
            (round_id, created_at),
        )
        self.conn.commit()
        return self.conn.execute("SELECT * FROM rounds WHERE id = ?", (round_id,)).fetchone()

    def current_question(self) -> sqlite3.Row:
        round_row = self.active_round()
        row = self.conn.execute(
            """
            SELECT * FROM questions
            WHERE round_id = ? AND final_result IS NULL
            ORDER BY question_number DESC
            LIMIT 1
            """,
            (round_row["id"],),
        ).fetchone()
        if row:
            return row
        last_number = self.conn.execute(
            "SELECT COALESCE(MAX(question_number), 0) FROM questions WHERE round_id = ?",
            (round_row["id"],),
        ).fetchone()[0]
        cur = self.conn.execute(
            """
            INSERT INTO questions (round_id, question_number, created_at, subject)
            VALUES (?, ?, ?, (SELECT subject FROM round_subjects WHERE round_id=? AND question_number=?))
            """,
            (round_row["id"], last_number + 1, utc_now(), round_row["id"], last_number + 1),
        )
        self.conn.commit()
        return self.conn.execute("SELECT * FROM questions WHERE id = ?", (cur.lastrowid,)).fetchone()

    def load_round(self, round_id: int) -> None:
        if not self.conn.execute("SELECT id FROM rounds WHERE id=?", (round_id,)).fetchone():
            raise ValueError("Game not found")
        with self.conn:
            self.conn.execute("UPDATE rounds SET active=0 WHERE active=1")
            self.conn.execute("UPDATE rounds SET active=1 WHERE id=?", (round_id,))

    def undo_last_attempt(self) -> dict:
        round_id = self.active_round()["id"]
        attempt = self.conn.execute("""SELECT a.id, a.question_id, q.question_number FROM attempts a
            JOIN questions q ON q.id=a.question_id WHERE q.round_id=?
            ORDER BY q.question_number DESC, a.attempt_order DESC LIMIT 1""", (round_id,)).fetchone()
        if not attempt:
            return {"accepted": False, "reason": "No recorded entry to undo"}
        with self.conn:
            self.conn.execute("DELETE FROM attempts WHERE id=?", (attempt['id'],))
            self.conn.execute("UPDATE questions SET final_result=NULL, finalized_at=NULL WHERE id=?", (attempt['question_id'],))
            self.conn.execute("""DELETE FROM questions WHERE round_id=? AND question_number>?
                AND id NOT IN (SELECT question_id FROM attempts)""", (round_id, attempt['question_number']))
        return {"accepted": True, "question_number": attempt['question_number']}

    def attempts_for_question(self, question_id: int) -> list[Attempt]:
        rows = self.conn.execute(
            "SELECT * FROM attempts WHERE question_id = ? ORDER BY attempt_order",
            (question_id,),
        ).fetchall()
        return [self._attempt_from_row(row) for row in rows]

    @staticmethod
    def _attempt_from_row(row: sqlite3.Row) -> Attempt:
        values = dict(row)
        values["interrupt"] = (
            None if values["interrupt"] is None else bool(values["interrupt"])
        )
        values["correct"] = (
            None if values["correct"] is None else bool(values["correct"])
        )
        return Attempt(**values)

    def add_attempt(
        self,
        player_id: int | None,
        team: str | None,
        elapsed_ms: int | None,
        result: str,
        *,
        interrupt: bool | None = None,
        correct: bool | None = None,
        person_id: str | None = None,
        player_name: str | None = None,
    ) -> Attempt:
        question = self.current_question()
        next_order = len(self.attempts_for_question(question["id"])) + 1
        cur = self.conn.execute(
            """
            INSERT INTO attempts
                (question_id, attempt_order, player_id, team, elapsed_ms, result,
                 interrupt, correct, created_at, person_id, player_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question["id"],
                next_order,
                player_id,
                team,
                elapsed_ms,
                result,
                interrupt,
                correct,
                utc_now(),
                person_id,
                player_name,
            ),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM attempts WHERE id = ?", (cur.lastrowid,)).fetchone()
        return self._attempt_from_row(row)

    def delete_last_unfinalized_attempt(self) -> bool:
        question = self.current_question()
        row = self.conn.execute(
            """
            SELECT id FROM attempts
            WHERE question_id = ?
            ORDER BY attempt_order DESC
            LIMIT 1
            """,
            (question["id"],),
        ).fetchone()
        if not row:
            return False
        self.conn.execute("DELETE FROM attempts WHERE id = ?", (row["id"],))
        self.conn.commit()
        return True

    def finalize_current_question(self, final_result: str, subject: str | None = None) -> None:
        question = self.current_question()
        self.conn.execute(
            """
            UPDATE questions
            SET final_result = ?, subject = COALESCE(?, subject), finalized_at = ?
            WHERE id = ?
            """,
            (final_result, subject, utc_now(), question["id"]),
        )
        round_id = question["round_id"]
        next_number = question["question_number"] + 1
        self.conn.execute(
            """
            INSERT INTO questions (round_id, question_number, created_at, subject)
            VALUES (?, ?, ?, (SELECT subject FROM round_subjects WHERE round_id=? AND question_number=?))
            """,
            (round_id, next_number, utc_now(), round_id, next_number),
        )
        self.conn.commit()

    def set_subjects(self, subjects: dict[int, str], round_id: int | None = None, source_url: str = "") -> int:
        round_id = round_id or self.active_round()["id"]
        if not self.conn.execute("SELECT id FROM rounds WHERE id=?", (round_id,)).fetchone():
            raise ValueError("Game not found")
        count = 0
        self.conn.execute("DELETE FROM round_subjects WHERE round_id=?", (round_id,))
        self.conn.execute("UPDATE questions SET subject=NULL WHERE round_id=?", (round_id,))
        for question_number, subject in subjects.items():
            self.conn.execute("INSERT INTO round_subjects VALUES (?, ?, ?)", (round_id, question_number, subject))
            cur = self.conn.execute(
                """
                UPDATE questions
                SET subject = ?
                WHERE round_id = ? AND question_number = ?
                """,
                (subject, round_id, question_number),
            )
            count += cur.rowcount
        self.conn.commit()
        self.set_setting(f"pdf:{round_id}", source_url)
        return count

    def get_setting(self, key: str, default=None):
        row = self.conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key: str, value) -> None:
        self.conn.execute("INSERT OR REPLACE INTO app_settings VALUES (?, ?)", (key, json.dumps(value)))
        self.conn.commit()

    def roster(self) -> dict[str, dict]:
        return self.get_setting("roster", {})

    def set_roster(self, rows: list[dict]) -> None:
        from .roster import validate_roster
        self.set_setting("roster", validate_roster(rows))

    def player_identity(self, port: int) -> tuple[str | None, str]:
        player = self.roster().get(str(port), {})
        return player.get("person_id") or None, player.get("name") or f"P{port}"

    def rounds_list(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM rounds ORDER BY id DESC")]

    def game_payload(self, round_id: int | None = None) -> dict:
        round_id = round_id or self.active_round()["id"]
        game = self.conn.execute("SELECT * FROM rounds WHERE id=?", (round_id,)).fetchone()
        if not game:
            raise ValueError("Game not found")
        game_key = f"{self.get_setting('device_id')}:{round_id}"
        rows = self.conn.execute("""SELECT a.*, q.question_number, q.subject FROM attempts a
            JOIN questions q ON q.id=a.question_id WHERE q.round_id=? ORDER BY q.question_number,a.attempt_order""",
            (round_id,)).fetchall()
        attempts = []
        for r in rows:
            row = dict(r)
            row.pop("team", None)
            row["attempt_key"] = f"{game_key}:{r['id']}"
            row["game_key"] = game_key
            row["game_name"] = game["name"]
            row["person_id"] = r["person_id"] or (f"unassigned:{game_key}:P{r['player_id']}" if r["player_id"] else "")
            row["player_name"] = r["player_name"] or (f"P{r['player_id']} (unassigned)" if r["player_id"] else "")
            row["interrupt"] = None if r["interrupt"] is None else bool(r["interrupt"])
            row["correct"] = None if r["correct"] is None else bool(r["correct"])
            attempts.append(row)
        questions = [dict(r) for r in self.conn.execute("""SELECT * FROM questions
            WHERE round_id=? AND (final_result IS NOT NULL OR id IN (SELECT question_id FROM attempts))
            ORDER BY question_number""", (round_id,))]
        missing = [r["question_number"] for r in questions if not r["subject"]]
        return {"game_key": game_key, "name": game["name"], "round_id": round_id,
                "created_at": game["created_at"], "pdf_url": self.get_setting(f"pdf:{round_id}", ""),
                "questions": questions, "attempts": attempts, "missing_subjects": missing}

    def subject_for_current_question(self) -> str | None:
        question = self.current_question()
        return question["subject"]

    def add_score(self, team: str, points: int, reason: str) -> None:
        round_row = self.active_round()
        self.conn.execute(
            """
            INSERT INTO score_events (round_id, team, points, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (round_row["id"], team, points, reason, utc_now()),
        )
        self.conn.commit()

    def scores(self) -> dict[str, int]:
        round_row = self.active_round()
        rows = self.conn.execute(
            """
            SELECT team, COALESCE(SUM(points), 0) AS total
            FROM score_events
            WHERE round_id = ?
            GROUP BY team
            """,
            (round_row["id"],),
        ).fetchall()
        totals = {"A": 0, "B": 0}
        for row in rows:
            totals[row["team"]] = int(row["total"])
        return totals

    def state_snapshot(self) -> dict[str, Any]:
        round_row = self.active_round()
        question = self.current_question()
        subject = self.conn.execute("SELECT subject FROM round_subjects WHERE round_id=? AND question_number=?",
                                    (round_row["id"], question["question_number"])).fetchone()
        if subject and question["subject"] != subject[0]:
            self.conn.execute("UPDATE questions SET subject=? WHERE id=?", (subject[0], question["id"]))
            self.conn.commit()
            question = self.current_question()
        attempts = self.attempts_for_question(question["id"])
        return {
            "round": dict(round_row),
            "question": dict(question),
            "attempts": [attempt.__dict__ for attempt in attempts],
            "scores": self.scores(),
            "players": self.roster(),
        }

    def round_sheet_rows(self) -> list[list[str | int | float | None]]:
        round_row = self.active_round()
        rows = self.conn.execute(
            """
            SELECT * FROM questions
            WHERE round_id = ? AND final_result IS NOT NULL
            ORDER BY question_number
            """,
            (round_row["id"],),
        ).fetchall()
        sheet_rows: list[list[str | int | float | None]] = [
            [
                "question",
                "subject",
                "final_result",
                "attempt_1_player",
                "attempt_1_result",
                "attempt_1_interrupt",
                "attempt_1_correct",
                "attempt_1_time_s",
                "attempt_2_player",
                "attempt_2_result",
                "attempt_2_interrupt",
                "attempt_2_correct",
                "attempt_2_time_s",
            ]
        ]
        for row in rows:
            attempts = self.attempts_for_question(row["id"])
            values: list[str | int | float | None] = [
                row["question_number"],
                row["subject"],
                row["final_result"],
            ]
            for attempt in attempts[:2]:
                values.extend(
                    [
                        attempt.player_id,
                        attempt.result,
                        self._bool_cell(attempt.interrupt),
                        self._bool_cell(attempt.correct),
                        None if attempt.elapsed_ms is None else round(attempt.elapsed_ms / 1000, 2),
                    ]
                )
            while len(values) < len(sheet_rows[0]):
                values.append("")
            sheet_rows.append(values)
        return sheet_rows

    @staticmethod
    def _bool_cell(value: bool | None) -> str:
        if value is None:
            return ""
        return "true" if value else "false"

    def export_csv(self, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerows(self.round_sheet_rows())
        return output
