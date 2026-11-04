from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ScoreDisplay(Protocol):
    def show_scores(self, team_a: int, team_b: int) -> None: ...


class NoopScoreDisplay:
    """Used on development machines and when no physical display is connected."""

    def show_scores(self, team_a: int, team_b: int) -> None:
        return None


@dataclass
class MAX7219ScoreDisplay:
    """Two daisy-chained eight-digit MAX7219 modules on Raspberry Pi SPI0.

    The module nearest the Pi's DIN wire is Team B; its DOUT feeds Team A.
    """

    device: int = 0
    brightness: int = 4

    def __post_init__(self) -> None:
        try:
            import spidev  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "MAX7219 output needs the 'spidev' package on the Raspberry Pi. "
                "Install it with: python3 -m pip install spidev"
            ) from exc
        self._spi = spidev.SpiDev()
        self._spi.open(0, self.device)
        self._spi.max_speed_hz = 1_000_000
        self._spi.mode = 0
        self._configure()

    def _send(self, register: int, team_b_value: int, team_a_value: int) -> None:
        # SPI shifts through the near module first, so far-module bytes go first.
        self._spi.xfer2([register, team_a_value, register, team_b_value])

    def _configure(self) -> None:
        self._send(0x0C, 1, 1)
        self._send(0x0F, 0, 0)
        self._send(0x0B, 7, 7)
        level = max(0, min(15, self.brightness))
        self._send(0x0A, level, level)
        self._send(0x09, 0, 0)
        self._clear()

    def _clear(self) -> None:
        for digit in range(1, 9):
            self._send(digit, 0, 0)

    @staticmethod
    def _digits(score: int, label: int) -> list[int]:
        """Eight raw-segment bytes, left-to-right: label plus seven digits."""
        score = max(0, min(9_999_999, score))
        numerals = (0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F)
        text = str(score)
        blank_count = 7 - len(text)
        return [label, *([0] * blank_count), *(numerals[int(char)] for char in text)]

    def show_scores(self, team_a: int, team_b: int) -> None:
        a_digits = self._digits(team_a, 0x77)  # A
        b_digits = self._digits(team_b, 0x7C)  # b
        # MAX7219 digit register 1 is the rightmost physical digit.
        for register, index in enumerate(range(7, -1, -1), start=1):
            self._send(register, b_digits[index], a_digits[index])

    def close(self) -> None:
        self._clear()
        self._spi.close()


def build_score_display(enabled: bool) -> ScoreDisplay:
    return MAX7219ScoreDisplay() if enabled else NoopScoreDisplay()
