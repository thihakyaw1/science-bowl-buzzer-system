from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class KeypadCommand:
    action: str
    team: str | None = None
    points: int | None = None
    reason: str | None = None


KEY_COMMANDS = {
    "KEY_KP0": KeypadCommand("reset"),
    "KEY_KP1": KeypadCommand("correct"),
    "KEY_KP2": KeypadCommand("wrong"),
    "KEY_KP3": KeypadCommand("timer"),
    "KEY_KP4": KeypadCommand("score", "A", 4, "Toss-up"),
    "KEY_KP5": KeypadCommand("score", "B", 4, "Toss-up"),
    "KEY_KP7": KeypadCommand("score", "A", 10, "Bonus"),
    "KEY_KP8": KeypadCommand("score", "B", 10, "Bonus"),
    "KEY_KPDOT": KeypadCommand("delete"),
    # These aliases make a compact keyboard usable during development.
    "KEY_0": KeypadCommand("reset"),
    "KEY_1": KeypadCommand("correct"),
    "KEY_2": KeypadCommand("wrong"),
    "KEY_3": KeypadCommand("timer"),
    "KEY_4": KeypadCommand("score", "A", 4, "Toss-up"),
    "KEY_5": KeypadCommand("score", "B", 4, "Toss-up"),
    "KEY_7": KeypadCommand("score", "A", 10, "Bonus"),
    "KEY_8": KeypadCommand("score", "B", 10, "Bonus"),
    "KEY_DELETE": KeypadCommand("delete"),
}


def command_for_key_code(key_code: str) -> KeypadCommand | None:
    return KEY_COMMANDS.get(key_code)


class KeypadSource(Protocol):
    def read_commands(self) -> list[KeypadCommand]:
        ...


class EvdevNumericKeypad:
    """Reads press events from a USB numeric keypad on Linux."""

    def __init__(self, device_path: str = "auto") -> None:
        try:
            from evdev import InputDevice, ecodes, list_devices
        except ImportError as exc:
            raise RuntimeError(
                "Direct USB keypad input needs the evdev package on the Raspberry Pi"
            ) from exc

        self._ecodes = ecodes
        if device_path == "auto":
            device_path = self._find_numeric_keypad(InputDevice, ecodes, list_devices)
        self.device_path = device_path
        self.device = InputDevice(device_path)

    @staticmethod
    def _find_numeric_keypad(InputDevice, ecodes, list_devices) -> str:
        matches: list[str] = []
        for path in list_devices():
            device = InputDevice(path)
            try:
                keys = set(device.capabilities().get(ecodes.EV_KEY, []))
                if ecodes.KEY_KP0 in keys and ecodes.KEY_KPENTER in keys:
                    matches.append(path)
            finally:
                device.close()

        if not matches:
            raise RuntimeError("No USB numeric keypad was found under /dev/input")
        if len(matches) > 1:
            raise RuntimeError(
                "More than one numeric keypad was found; use --keypad-device with "
                "a specific /dev/input/by-id/...-event-kbd path"
            )
        return matches[0]

    def read_commands(self) -> list[KeypadCommand]:
        commands: list[KeypadCommand] = []
        try:
            events = self.device.read()
        except BlockingIOError:
            return commands

        for event in events:
            if event.type != self._ecodes.EV_KEY or event.value != 1:
                continue
            key_code = self._ecodes.KEY.get(event.code)
            if not isinstance(key_code, str):
                continue
            command = command_for_key_code(key_code)
            if command is not None:
                commands.append(command)
        return commands

    def close(self) -> None:
        self.device.close()
