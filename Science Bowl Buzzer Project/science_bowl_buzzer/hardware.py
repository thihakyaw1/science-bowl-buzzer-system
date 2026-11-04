from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol


class InputSource(Protocol):
    """Reads contestant winner lines.

    Implementations return a sequence of player numbers whose digital input is
    active. The existing buzzer controller should normally allow only one active
    winner at a time.
    """

    def read_active_players(self) -> list[int]:
        ...


class ResetOutput(Protocol):
    """Triggers the original controller reset line."""

    available: bool

    def pulse(self) -> None:
        ...


@dataclass
class MockInputSource:
    active_players: list[int]

    def __init__(self) -> None:
        self.active_players = []

    def set_active(self, player: int | None) -> None:
        self.active_players = [] if player is None else [player]

    def read_active_players(self) -> list[int]:
        return list(self.active_players)


class NoopResetOutput:
    available = False

    def pulse(self) -> None:
        return None


class GpioZeroResetOutput:
    """Drives the LED side of an isolated PhotoMOS reset circuit."""

    available = True

    def __init__(self, gpio_pin: int = 17, pulse_seconds: float = 0.15) -> None:
        if pulse_seconds <= 0:
            raise ValueError("pulse_seconds must be positive")
        try:
            from gpiozero import OutputDevice
        except ImportError as exc:
            raise RuntimeError(
                "GPIO reset output needs gpiozero on the Raspberry Pi"
            ) from exc

        self.pulse_seconds = pulse_seconds
        self.device = OutputDevice(gpio_pin, active_high=True, initial_value=False)

    def pulse(self) -> None:
        self.device.on()
        try:
            time.sleep(self.pulse_seconds)
        finally:
            self.device.off()

    def close(self) -> None:
        self.device.off()
        self.device.close()


class Mcp23017InputSource:
    """MCP23017 reader for the isolated optocoupler detector.

    This assumes 16 optocoupler collector outputs are wired to GPA0..GPA7 and
    GPB0..GPB7. Each input is pulled up to 3.3 V and goes low for a winner. Raw
    buzzer signals never connect electrically to the Raspberry Pi or MCP23017.
    """

    IODIRA = 0x00
    IODIRB = 0x01
    GPPUA = 0x0C
    GPPUB = 0x0D
    GPIOA = 0x12
    GPIOB = 0x13

    # Physical detector channel (old label) -> displayed port (new label).
    PLAYER_MAP = {3: 1, 4: 2, 11: 3, 10: 4, 16: 5, 15: 6, 6: 7, 5: 8,
                  1: 9, 2: 10, 12: 11, 9: 12, 13: 13, 14: 14, 8: 15, 7: 16}

    def __init__(
        self,
        address: int = 0x20,
        bus_number: int = 1,
        active_low: bool = True,
        enabled_players: Iterable[int] = range(1, 17),
    ) -> None:
        try:
            from smbus2 import SMBus
        except ImportError as exc:
            raise RuntimeError("Install smbus2 on the Raspberry Pi for MCP23017 input") from exc

        self.bus = SMBus(bus_number)
        self.address = address
        self.active_low = active_low
        self.enabled_players = set(enabled_players)
        self.bus.write_byte_data(self.address, self.IODIRA, 0xFF)
        self.bus.write_byte_data(self.address, self.IODIRB, 0xFF)
        pullups = 0xFF if active_low else 0x00
        self.bus.write_byte_data(self.address, self.GPPUA, pullups)
        self.bus.write_byte_data(self.address, self.GPPUB, pullups)

    def read_active_players(self) -> list[int]:
        gpioa = self.bus.read_byte_data(self.address, self.GPIOA)
        gpiob = self.bus.read_byte_data(self.address, self.GPIOB)
        mask = gpioa | (gpiob << 8)
        active: list[int] = []
        for player in range(1, 17):
            bit_set = bool(mask & (1 << (player - 1)))
            is_active = not bit_set if self.active_low else bit_set
            mapped_player = self.PLAYER_MAP[player]
            if is_active and mapped_player in self.enabled_players:
                active.append(mapped_player)
        return sorted(active)

    def close(self) -> None:
        self.bus.close()


class WinnerInputPoller:
    """Debounces a latched winner input and emits one event per reset cycle."""

    def __init__(
        self,
        source: InputSource,
        on_winner: Callable[[int], object],
        stable_reads: int = 2,
    ) -> None:
        if stable_reads < 1:
            raise ValueError("stable_reads must be at least 1")
        self.source = source
        self.on_winner = on_winner
        self.stable_reads = stable_reads
        self.active_players: list[int] = []
        self.last_error: str | None = None
        # Require one all-clear read after startup. This prevents an old winner
        # that was already latched when the app started from becoming a new log.
        self._armed = False
        self._candidate: int | None = None
        self._candidate_reads = 0

    def poll(self) -> None:
        try:
            active = sorted(set(self.source.read_active_players()))
        except Exception as exc:
            self.last_error = f"MCP23017 read failed: {exc}"
            return

        self.active_players = active
        if not active:
            self._armed = True
            self._candidate = None
            self._candidate_reads = 0
            self.last_error = None
            return

        if len(active) > 1:
            self._armed = False
            self._candidate = None
            self._candidate_reads = 0
            self.last_error = "Multiple winner inputs are active: " + ", ".join(
                str(player) for player in active
            )
            return

        if not self._armed:
            return

        player = active[0]
        if self._candidate == player:
            self._candidate_reads += 1
        else:
            self._candidate = player
            self._candidate_reads = 1

        if self._candidate_reads >= self.stable_reads:
            self.on_winner(player)
            self._armed = False
            self.last_error = None
