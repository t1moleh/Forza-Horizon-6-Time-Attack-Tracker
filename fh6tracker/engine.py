"""LapEngine - die reine Mess-Logik (kein Netzwerk, keine Dateien).

Wird mit (Zeit, Paket) gefuettert und liefert Runden-Ereignisse zurueck.
Genau diese Engine verarbeitet sowohl Live-UDP-Pakete als auch ein Replay
der aufgezeichneten ta_trace.csv - so kann gegen echte Daten kalibriert und
in Tests gegen synthetische Streams geprueft werden.

Zwei Betriebsarten, automatisch:
  * Bekannte Strecke (aus CircuitStore): wird per Position sofort
    wiedererkannt -> ARMED. Die erste Linien-Ueberquerung startet die
    Zeit, jede weitere stoppt eine Runde. Alle Runden praezise
    (Linien-Ueberquerung + Zeit-Interpolation).
  * Unbekannte Strecke: Schleifenschluss-Erkennung findet die Start/Ziel-
    Linie selbst, leitet das Heading aus der Fahrtrichtung ab und legt ein
    LineGate an. Die so entdeckte erste Runde ist naeherungsweise; ab dann
    praezise.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable

from . import geometry as g
from .circuits import Circuit
from .gate import LineGate
from .telemetry import Packet


@dataclass(frozen=True)
class EngineConfig:
    sample_dist: float = 5.0       # Stuetzpunkt-Abstand (m) fuer die Historie
    match_radius: float = 40.0     # Schleifenschluss: Naehe zu altem Punkt (m)
    min_lap_s: float = 15.0        # Mindest-Rundendauer (gegen Fehlausloeser)
    min_lap_dist: float = 500.0    # Mindest-Streckenlaenge einer Runde (m)
    recognize_radius: float = 150.0  # Naehe zum Mittelpunkt fuer Wiedererkennung
    history_max: int = 4000
    max_lap_s: float = 240.0       # laenger -> Runde verworfen (Track verlassen)


@dataclass(frozen=True)
class LapEvent:
    lap_time: float          # Rundenzeit (s)
    crossing_time: float     # interpolierter Zeitpunkt der Ziel-Ueberquerung
    circuit: str             # Streckenname
    car: Packet              # Fahrzeug-/Telemetrie-Snapshot beim Ziel
    approximate: bool        # True = via Schleifenschluss entdeckte erste Runde
    profile: tuple = ()      # ((lap_dist, elapsed), ...) - fuer Ghost-Vergleich


class LapEngine:
    def __init__(
        self,
        circuits: list[Circuit] | None = None,
        config: EngineConfig | None = None,
        namer: Callable[[g.Vec, g.Vec], str] | None = None,
    ):
        self.circuits = circuits or []
        self.cfg = config or EngineConfig()
        # namer: bekommt (center, heading) einer NEU entdeckten Linie und gibt
        # einen Namen zurueck (und persistiert sie typischerweise). Default zaehlt.
        self._namer = namer or self._default_namer
        self._auto_n = 0

        self.gate: LineGate | None = None
        self.circuit_name: str | None = None
        self._reset_run()

    # -- oeffentlich ---------------------------------------------------------

    def set_active_circuit(self, circuit: Circuit) -> None:
        """Setzt die aktive Strecke (z. B. nach Wiedererkennung) -> ARMED."""
        self.gate = circuit.gate()
        self.circuit_name = circuit.name
        self._clear_lap()  # ARMED: erste Ueberquerung startet die Zeit

    def update(self, t: float, pkt: Packet) -> LapEvent | None:
        """Verarbeitet ein Paket zum Zeitpunkt t. Gibt ggf. eine fertige Runde."""
        if not pkt.race_on:
            # Welt verlassen (z. B. Garage/Autowechsel): laufende Messung
            # zuruecksetzen, aber bekannte Linie BEHALTEN -> nach Rueckkehr
            # sofort wieder scharf, ohne neue Lern-Runde.
            self._reset_run()
            return None

        cur = (pkt.x, pkt.z)

        step = g.dist(cur, self.prev_xz) if self.prev is not None else 0.0
        self.path_dist += step

        # Stuetzpunkte alle sample_dist Meter
        if not self.history or (self.path_dist - self.history[-1][3]) >= self.cfg.sample_dist:
            self.history.append((t, pkt.x, pkt.z, self.path_dist))
            if len(self.history) > self.cfg.history_max:
                self.history.popleft()

        # Laufende Runde: Distanz + Profil (lap_dist -> elapsed) fuer den
        # Ghost-Vergleich aufzeichnen.
        if self.gate is not None and self.lap_start_t is not None and self.prev is not None:
            self.lap_dist += step
            if self.lap_dist - self._last_prof_dist >= self.cfg.sample_dist:
                self._last_prof_dist = self.lap_dist
                self.lap_profile.append((self.lap_dist, t - self.lap_start_t))

        # Wiedererkennung bekannter Strecke - inkl. Umschalten zwischen
        # Strecken: betritt man den Startbereich einer ANDEREN bekannten Strecke
        # (und ist vom aktuellen Start entfernt), wird umgeklinkt.
        if self.circuits:
            c = self._nearest_known(pkt.x, pkt.z)
            if c is not None:
                if self.gate is None:
                    self.set_active_circuit(c)
                elif c.name != self.circuit_name and \
                        g.dist(cur, self.gate.center) > self.cfg.recognize_radius:
                    self.set_active_circuit(c)

        # Runden-Abbruch: laeuft die Runde unrealistisch lange (Track verlassen /
        # frei herumgefahren), Messung verwerfen -> zurueck in ARMED.
        if self.lap_start_t is not None and (t - self.lap_start_t) > self.cfg.max_lap_s:
            self._clear_lap()

        event: LapEvent | None = None
        if self.gate is not None:
            event = self._update_with_gate(t, pkt, cur)
        else:
            event = self._update_searching(t, pkt, cur)

        self.prev = t
        self.prev_xz = cur
        return event

    # -- intern --------------------------------------------------------------

    def _reset_run(self) -> None:
        self.prev: float | None = None
        self.prev_xz: g.Vec = (0.0, 0.0)
        self.history: deque = deque()
        self.path_dist = 0.0
        self._clear_lap()

    def _clear_lap(self) -> None:
        # ARMED (Linie bekannt, aber Lauf neu): erste Ueberquerung startet Zeit.
        self.lap_start_t: float | None = None
        self.lap_dist = 0.0
        self.lap_profile: list[tuple[float, float]] = []
        self._last_prof_dist = 0.0

    def _start_lap(self, start_time: float) -> None:
        self.lap_start_t = start_time
        self.lap_dist = 0.0
        self.lap_profile = []
        self._last_prof_dist = 0.0

    def _default_namer(self, center: g.Vec, heading: g.Vec) -> str:
        self._auto_n += 1
        return f"Strecke {self._auto_n}"

    def _nearest_known(self, x: float, z: float) -> Circuit | None:
        best, best_d = None, self.cfg.recognize_radius
        for c in self.circuits:
            d = g.dist((x, z), c.center)
            if d < best_d:
                best, best_d = c, d
        return best

    def _update_with_gate(self, t: float, pkt: Packet, cur: g.Vec) -> LapEvent | None:
        assert self.gate is not None
        if self.prev is None:
            return None
        crossing = self.gate.cross(self.prev_xz, self.prev, cur, t)
        if crossing is None:
            return None
        if self.lap_start_t is None:
            # ARMED -> erste Ueberquerung startet nur die Zeit.
            self._start_lap(crossing.time)
            return None
        lap = crossing.time - self.lap_start_t
        if lap < self.cfg.min_lap_s:
            # Zu kurz (Doppelausloeser/Wackler): Start NICHT verschieben.
            return None
        profile = tuple(self.lap_profile)
        self._start_lap(crossing.time)
        return LapEvent(lap, crossing.time, self.circuit_name or "?", pkt,
                        approximate=False, profile=profile)

    def _update_searching(self, t: float, pkt: Packet, cur: g.Vec) -> LapEvent | None:
        cfg = self.cfg
        for (pt, px, pz, pd) in self.history:
            if (t - pt) >= cfg.min_lap_s and (self.path_dist - pd) >= cfg.min_lap_dist \
                    and g.dist(cur, (px, pz)) <= cfg.match_radius:
                heading = self._heading_at(cur)
                if heading == (0.0, 0.0):
                    continue
                name = self._namer((px, pz), heading)
                self.gate = LineGate((px, pz), heading)
                self.circuit_name = name
                lap_time = t - pt          # erste Runde: naeherungsweise
                # ARMED: erst die naechste saubere Linien-Ueberquerung startet
                # die praezise Messung (vermeidet einmaligen Anfangs-Versatz).
                self._clear_lap()
                return LapEvent(lap_time, t, name, pkt, approximate=True)
        return None

    def _heading_at(self, cur: g.Vec) -> g.Vec:
        """Aktuelle Fahrtrichtung (fuer die Ausrichtung der entdeckten Linie)."""
        if self.prev is None:
            return (0.0, 0.0)
        return g.normalize(g.sub(cur, self.prev_xz))
