from __future__ import annotations

from science_bowl_buzzer.hardware import WinnerInputPoller
from science_bowl_buzzer.keypad import KeypadCommand, command_for_key_code
from science_bowl_buzzer.match import MatchController
from science_bowl_buzzer.server import HardwareRuntime
from science_bowl_buzzer.storage import Database


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


def test_winner_poller_debounces_and_emits_once_until_clear():
    source = FakeInputSource()
    winners: list[int] = []
    poller = WinnerInputPoller(source, winners.append, stable_reads=2)

    poller.poll()
    source.active = [4]
    poller.poll()
    assert winners == []
    poller.poll()
    poller.poll()
    assert winners == [4]

    source.active = []
    poller.poll()
    source.active = [9]
    poller.poll()
    poller.poll()
    assert winners == [4, 9]


def test_winner_poller_rejects_multiple_active_lines_until_all_clear():
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


def test_winner_poller_requires_clear_state_after_startup():
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


def test_numeric_keypad_mapping():
    assert command_for_key_code("KEY_KP1") == KeypadCommand("correct")
    assert command_for_key_code("KEY_KP8") == KeypadCommand(
        "score", "B", 10, "Bonus"
    )
    assert command_for_key_code("KEY_KP6") is None


def test_hardware_runtime_dispatches_keypad_score(tmp_path):
    controller = MatchController(Database(tmp_path / "runtime.db"))
    keypad = FakeKeypad([KeypadCommand("score", "A", 4, "Toss-up")])
    runtime = HardwareRuntime(controller, keypad_source=keypad)

    runtime.poll()

    assert controller.snapshot()["scores"] == {"A": 4, "B": 0}
