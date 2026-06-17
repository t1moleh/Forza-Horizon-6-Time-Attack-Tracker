"""Session-Zustand: alles zur aktuell laufenden Tool-Sitzung.

Eine Session = ein durchgehender Tool-Lauf. Sie kann mehrere Fahrzeuge und
Strecken umfassen (Fahrzeugwechsel werden mitgezaehlt) - so muss man nicht
fuer jeden Autowechsel neu starten und kann Autos direkt vergleichen.

Thread-sicher: der UDP-Loop schreibt, der Webserver liest (Snapshot).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from .engine import LapEvent
from .telemetry import Packet
from .util import fmt_delta, fmt_time


@dataclass
class SessionLap:
    time_seconds: float
    car_ordinal: int
    car_name: str
    car_class: str
    pi: int
    track: str
    timestamp: float          # perf_counter beim Ziel
    approximate: bool
    is_best: bool = False     # Session-Bestzeit dieser (Auto, Strecke)-Kombi


@dataclass
class CarInfo:
    ordinal: int
    name: str
    car_class: str
    pi: int
    drivetrain: str


class SessionState:
    """Geteilter, thread-sicherer Zustand der laufenden Session."""

    def __init__(self):
        self._lock = threading.Lock()
        self.started_at = time.time()
        self._start_perf = time.perf_counter()

        self.connected = False        # ueberhaupt Pakete empfangen?
        self.in_world = False         # race_on
        self.current_car: CarInfo | None = None
        self.current_track: str | None = None
        self.armed = False            # Linie bekannt + Messung scharf/laufend
        self._lap_start_perf: float | None = None
        self._live_delta: float | None = None   # Live-Delta zur Bestzeit (Ghost)
        self._telemetry: dict | None = None      # letzte Live-Telemetrie

        self.laps: list[SessionLap] = []
        self._cars: dict[int, CarInfo] = {}

    # -- vom UDP-Loop geschrieben -------------------------------------------

    def note_packet(self, pkt: Packet, names_display) -> None:
        with self._lock:
            self.connected = True
            self.in_world = bool(pkt.race_on)
            if pkt.race_on:
                car = CarInfo(pkt.ordinal, names_display(pkt.ordinal),
                              pkt.class_name, pkt.pi, pkt.drivetrain_name)
                self.current_car = car
                self._cars[pkt.ordinal] = car

    def note_telemetry(self, telem: dict | None) -> None:
        with self._lock:
            self._telemetry = telem

    def note_engine(self, circuit_name: str | None, lap_start_perf: float | None,
                    live_delta: float | None = None) -> None:
        with self._lock:
            self.current_track = circuit_name
            self.armed = lap_start_perf is not None
            self._lap_start_perf = lap_start_perf
            self._live_delta = live_delta

    def add_lap(self, ev: LapEvent, car_name: str) -> bool:
        """Runde aufnehmen. Gibt True zurueck, wenn es eine neue Session-Bestzeit
        dieser (Auto, Strecke)-Kombi ist."""
        with self._lock:
            is_best = False
            if not ev.approximate:
                prev = [lp.time_seconds for lp in self.laps
                        if not lp.approximate and lp.car_ordinal == ev.car.ordinal
                        and lp.track == ev.circuit]
                is_best = not prev or ev.lap_time < min(prev)
            self.laps.append(SessionLap(
                time_seconds=ev.lap_time,
                car_ordinal=ev.car.ordinal,
                car_name=car_name,
                car_class=ev.car.class_name,
                pi=ev.car.pi,
                track=ev.circuit,
                timestamp=time.perf_counter(),
                approximate=ev.approximate,
                is_best=is_best,
            ))
            return is_best

    # -- vom Webserver gelesen ----------------------------------------------

    def snapshot(self) -> dict:
        """Aktueller Session-Teil des JSON-Vertrags."""
        with self._lock:
            now = time.perf_counter()
            current_lap = (now - self._lap_start_perf) if self._lap_start_perf else None

            valid = [lp for lp in self.laps if not lp.approximate]
            best = min(valid, key=lambda lp: lp.time_seconds) if valid else None

            cars_used = []
            for ordn, car in self._cars.items():
                car_laps = [lp for lp in valid if lp.car_ordinal == ordn]
                cars_used.append({
                    "ordinal": ordn,
                    "car_name": car.name,
                    "class": car.car_class,
                    "pi": car.pi,
                    "lap_count": len(car_laps),
                    "best": fmt_time(min((lp.time_seconds for lp in car_laps), default=None)),
                })

            return {
                "started_at": self.started_at,
                "duration_seconds": round(now - self._start_perf, 1),
                "current_car": self._car_dict(self.current_car),
                "current_track": self.current_track,
                "current_lap_seconds": round(current_lap, 3) if current_lap else None,
                "current_lap": fmt_time(current_lap) if current_lap else None,
                "current_delta_seconds": round(self._live_delta, 3) if self._live_delta is not None else None,
                "current_delta": fmt_delta(self._live_delta),
                "armed": self.armed,
                "session_best": self._lap_dict(best),
                "last_laps": [self._lap_dict(lp) for lp in reversed(valid[-5:])],
                "cars_used": cars_used,
                "lap_count": len(valid),
                "telemetry": self._telemetry if self.in_world else None,
            }

    @staticmethod
    def _car_dict(car: CarInfo | None) -> dict | None:
        if car is None:
            return None
        return {"ordinal": car.ordinal, "name": car.name, "class": car.car_class,
                "pi": car.pi, "drivetrain": car.drivetrain}

    @staticmethod
    def _lap_dict(lp: SessionLap | None) -> dict | None:
        if lp is None:
            return None
        return {
            "time_seconds": round(lp.time_seconds, 3),
            "time": fmt_time(lp.time_seconds),
            "car_ordinal": lp.car_ordinal,
            "car_name": lp.car_name,
            "class": lp.car_class,
            "pi": lp.pi,
            "track": lp.track,
            "is_best": lp.is_best,
        }
