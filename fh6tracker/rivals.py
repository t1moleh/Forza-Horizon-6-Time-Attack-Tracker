"""Rivals-Modus: Runden aus dem spielinternen Lap-Timer (statt GPS-Stoppuhr).

Anders als im Open-World-Time-Attack befuellt Forza im Rivals-Modus die Lap-
Timer-Felder (LastLapTime/BestLapTime/LapNumber, RaceOn=1). Hier werten wir sie
aus: eine Runde gilt als fertig, sobald LapNumber hochzaehlt - ihre Zeit ist
dann die frisch gesetzte LastLapTime. Die Strecken-Identitaet kommt weiter aus
der Positions-Erkennung (LapEngine/Circuits), die ZEIT aber aus dem Spiel.
"""
from __future__ import annotations

from dataclasses import dataclass


def is_rivals(lt: dict | None) -> bool:
    """True, wenn der spielinterne Lap-Timer aktiv ist (Rivals/strukturierter
    getimter Modus) - im Open-World-Time-Attack sind diese Felder 0."""
    if not lt or not lt.get("race_on"):
        return False
    return bool(lt.get("lap_number") or lt.get("best_lap")
                or lt.get("current_lap") or lt.get("last_lap"))


@dataclass(frozen=True)
class RivalsLap:
    lap_time: float      # Sekunden, aus LastLapTime
    lap_number: int      # Nummer der FERTIGEN Runde


class RivalsTracker:
    """Erkennt fertige Runden aus dem spielinternen Lap-Timer.

    Eine Runde ist fertig, wenn LapNumber hochzaehlt; ihre Zeit ist die dann
    gueltige LastLapTime. Run-Neustart (LapNumber faellt) und Verlassen der
    Session (race_on=0 / Felder 0) setzen sauber zurueck.
    """

    def __init__(self) -> None:
        self._prev_lap_num: int | None = None

    def reset(self) -> None:
        self._prev_lap_num = None

    def update(self, lt: dict | None) -> RivalsLap | None:
        """Pro Paket fuettern (lt = telemetry.parse_lap_timing). Gibt eine
        fertige Runde zurueck, sonst None."""
        if not is_rivals(lt):
            self._prev_lap_num = None      # Session/Run verlassen
            return None
        assert lt is not None
        ln = int(lt.get("lap_number") or 0)
        last = float(lt.get("last_lap") or 0.0)
        ev = None
        if self._prev_lap_num is not None and ln > self._prev_lap_num and last > 0:
            # LapNumber ist hochgezaehlt -> die vorige Runde ist fertig.
            ev = RivalsLap(lap_time=round(last, 3), lap_number=self._prev_lap_num)
        self._prev_lap_num = ln
        return ev
