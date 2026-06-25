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
    is_record: bool = False   # persoenliche Bestzeit all-time (Auto, Strecke)
    mode: str = "timeattack"  # timeattack | rivals


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
        self._mode = "timeattack"                 # aktueller Live-Modus
        self._rivals_lap: float | None = None     # spielinterne CurrentLapTime (Rivals)
        self._rivals_track: str | None = None     # erkannte Rivals-Strecke

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

    def note_mode(self, mode: str) -> None:
        with self._lock:
            self._mode = mode

    def note_rivals(self, current_lap: float | None, track: str | None) -> None:
        """Spielinterne Live-Werte fuer den Rivals-Modus (laufende Rundenzeit +
        erkannte Strecke)."""
        with self._lock:
            self._rivals_lap = current_lap
            self._rivals_track = track

    def note_engine(self, circuit_name: str | None, lap_start_perf: float | None,
                    live_delta: float | None = None) -> None:
        with self._lock:
            self.current_track = circuit_name
            self.armed = lap_start_perf is not None
            self._lap_start_perf = lap_start_perf
            self._live_delta = live_delta

    def add_lap(self, ev: LapEvent, car_name: str, is_record: bool = False,
                mode: str = "timeattack") -> bool:
        """Runde aufnehmen. `is_record` = persoenliche Bestzeit all-time (vom
        Aufrufer ermittelt). Gibt True zurueck, wenn es eine neue Session-Bestzeit
        dieser (Auto, Strecke, Modus)-Kombi ist."""
        with self._lock:
            is_best = False
            if not ev.approximate:
                prev = [lp.time_seconds for lp in self.laps
                        if not lp.approximate and lp.car_ordinal == ev.car.ordinal
                        and lp.track == ev.circuit and lp.mode == mode]
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
                is_record=is_record,
                mode=mode,
            ))
            return is_best

    # -- vom Webserver gelesen ----------------------------------------------

    def snapshot(self) -> dict:
        """Aktueller Session-Teil des JSON-Vertrags."""
        with self._lock:
            now = time.perf_counter()
            # Laufende Rundenzeit + Strecke je Modus: im Rivals-Modus aus dem
            # Spiel-Timer (setzt sauber an der Ziellinie zurueck), sonst GPS.
            if self._mode == "rivals":
                cl = self._rivals_lap
                cur_track = self._rivals_track or self.current_track
                cur_delta = None
            else:
                cl = (now - self._lap_start_perf) if self._lap_start_perf else None
                cur_track = self.current_track
                cur_delta = self._live_delta

            valid = [lp for lp in self.laps if not lp.approximate]
            # Session-Daten je Modus getrennt (Time Attack / Rivals).
            modes = {m: self._mode_view(valid, m) for m in ("timeattack", "rivals")}
            live = modes.get(self._mode) or modes["timeattack"]

            return {
                "started_at": self.started_at,
                "duration_seconds": round(now - self._start_perf, 1),
                "current_car": self._car_dict(self.current_car),
                "current_track": cur_track,
                "current_lap_seconds": round(cl, 3) if cl else None,
                "current_lap": fmt_time(cl) if cl else None,
                "current_delta_seconds": round(cur_delta, 3) if cur_delta is not None else None,
                "current_delta": fmt_delta(cur_delta),
                "armed": self.armed,
                # Top-Level = Live-Modus (Abwaertskompat); session_modes = beide.
                "session_best": live["session_best"],
                "last_laps": live["last_laps"],
                "cars_used": live["cars_used"],
                "lap_count": live["lap_count"],
                "session_modes": modes,
                "telemetry": self._telemetry if self.in_world else None,
                "mode": self._mode,
            }

    def _mode_view(self, valid: list, mode: str) -> dict:
        """Session-Teil (Bestzeit/letzte Runden/Autos) fuer EINEN Modus."""
        laps = [lp for lp in valid if lp.mode == mode]
        best = min(laps, key=lambda lp: lp.time_seconds) if laps else None
        cars_used = []
        for ordn in dict.fromkeys(lp.car_ordinal for lp in laps):
            car = self._cars.get(ordn)
            car_laps = [lp for lp in laps if lp.car_ordinal == ordn]
            cars_used.append({
                "ordinal": ordn,
                "car_name": car.name if car else car_laps[0].car_name,
                "class": car.car_class if car else car_laps[0].car_class,
                "pi": car.pi if car else car_laps[0].pi,
                "lap_count": len(car_laps),
                "best": fmt_time(min(lp.time_seconds for lp in car_laps)),
            })
        return {
            "session_best": self._lap_dict(best),
            "last_laps": [self._lap_dict(lp) for lp in reversed(laps[-5:])],
            "cars_used": cars_used,
            "lap_count": len(laps),
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
            "is_record": lp.is_record,
        }
