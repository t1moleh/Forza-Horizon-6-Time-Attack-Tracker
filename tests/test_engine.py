"""Tests fuer die LapEngine gegen synthetische Paket-Streams."""
import math

import pytest

from fh6tracker.circuits import Circuit
from fh6tracker.engine import EngineConfig, LapEngine
from fh6tracker.telemetry import Packet


def pkt(x, z, race_on=1, ordinal=253, car_class=3, pi=700, drivetrain=1):
    return Packet(race_on=race_on, ordinal=ordinal, car_class=car_class,
                  pi=pi, drivetrain=drivetrain, x=x, z=z)


def circle_lap(cx, cz, radius, t0, t1, n):
    """Generiert (t, x, z) entlang eines Kreises - eine Runde von t0 bis t1.

    Start/Ende bei Winkel 0 (rechts vom Zentrum), gegen den Uhrzeigersinn.
    """
    out = []
    for i in range(n + 1):
        frac = i / n
        ang = 2 * math.pi * frac
        x = cx + radius * math.cos(ang)
        z = cz + radius * math.sin(ang)
        t = t0 + (t1 - t0) * frac
        out.append((t, x, z))
    return out


def test_known_circuit_times_laps_precisely():
    # Start/Ziel-Linie bei (radius, 0) relativ zum Kreiszentrum.
    cx, cz, radius = 0.0, 0.0, 120.0
    center = (cx + radius, cz)
    # Auf einem Kreis ist die Fahrtrichtung am Startpunkt (Winkel 0) +z.
    circ = Circuit(name="Test", center=center, heading=(0.0, 1.0))
    engine = LapEngine(circuits=[circ], config=EngineConfig(min_lap_dist=400.0))

    events = []
    # Drei Runden, je 30 s.
    for lap_i in range(3):
        for (t, x, z) in circle_lap(cx, cz, radius, lap_i * 30.0, (lap_i + 1) * 30.0, 200):
            ev = engine.update(t, pkt(x, z))
            if ev:
                events.append(ev)

    # Erste Ueberquerung = Start (kein Event), dann 2 volle Runden gemessen.
    assert len(events) == 2
    for ev in events:
        assert ev.approximate is False
        assert ev.circuit == "Test"
        assert ev.lap_time == pytest.approx(30.0, abs=0.3)


def test_unknown_circuit_is_learned_then_timed():
    cx, cz, radius = 1000.0, -2000.0, 100.0
    engine = LapEngine(circuits=[], config=EngineConfig(min_lap_dist=400.0))

    events = []
    # Mehrere Runden: 1x entdecken (Schaetzung), dann ARMED, dann praezise.
    for lap_i in range(5):
        for (t, x, z) in circle_lap(cx, cz, radius, lap_i * 25.0, (lap_i + 1) * 25.0, 200):
            ev = engine.update(t, pkt(x, z))
            if ev:
                events.append(ev)

    # Erste erkannte Runde ist die per Schleifenschluss entdeckte (Schaetzung).
    assert events[0].approximate is True
    # Danach praezise Runden.
    precise = [e for e in events if not e.approximate]
    assert len(precise) >= 1
    assert precise[-1].lap_time == pytest.approx(25.0, abs=0.5)
    # Eine Strecke wurde benannt.
    assert engine.circuit_name is not None


def test_race_off_keeps_known_gate_but_resets_lap():
    cx, cz, radius = 0.0, 0.0, 120.0
    center = (cx + radius, cz)
    circ = Circuit(name="Test", center=center, heading=(0.0, 1.0))
    engine = LapEngine(circuits=[circ], config=EngineConfig(min_lap_dist=400.0))

    # Halbe Runde fahren, dann Welt verlassen (Autowechsel).
    for (t, x, z) in circle_lap(cx, cz, radius, 0.0, 30.0, 200)[:100]:
        engine.update(t, pkt(x, z))
    engine.update(30.5, pkt(center[0], center[1], race_on=0))

    # Linie muss erhalten bleiben (keine neue Lern-Runde noetig).
    assert engine.gate is not None
    assert engine.circuit_name == "Test"
    # Laufende Messung wurde zurueckgesetzt.
    assert engine.lap_start_t is None


def test_switches_between_known_circuits():
    # Zwei weit auseinanderliegende Strecken; Fahrt von A nach B -> Umschalten.
    a = Circuit(name="A", center=(0.0, 0.0), heading=(1.0, 0.0))
    b = Circuit(name="B", center=(5000.0, 5000.0), heading=(1.0, 0.0))
    engine = LapEngine(circuits=[a, b])
    engine.update(0.0, pkt(0.0, 0.0))        # bei A -> A aktiv
    assert engine.circuit_name == "A"
    engine.update(1.0, pkt(300.0, 0.0))      # von A entfernt, noch nicht bei B
    assert engine.circuit_name == "A"
    engine.update(2.0, pkt(5000.0, 5000.0))  # im Startbereich von B -> umschalten
    assert engine.circuit_name == "B"


def test_lap_abandoned_when_too_long():
    # Linie bekannt, Lauf startet, dann ewig "herumfahren" ohne Ueberquerung
    # -> Runde wird verworfen (lap_start_t zurueck auf None), kein Timer mehr.
    center = (50.0, 0.0)
    circ = Circuit(name="T", center=center, heading=(0.0, 1.0))
    engine = LapEngine(circuits=[circ],
                       config=EngineConfig(max_lap_s=5.0, min_lap_dist=0.0))
    engine.update(0.0, pkt(50.0, -5.0))
    engine.update(1.0, pkt(50.0, 5.0))     # Ueberquerung -> ARMED -> Timer laeuft
    assert engine.lap_start_t is not None
    # weiter weg fahren ohne erneute Ueberquerung, Zeit laeuft > max_lap_s
    engine.update(3.0, pkt(50.0, 40.0))
    engine.update(9.0, pkt(50.0, 60.0))    # > 5 s seit Start -> verworfen
    assert engine.lap_start_t is None


def test_min_lap_filter_rejects_too_short():
    center = (50.0, 0.0)
    circ = Circuit(name="T", center=center, heading=(0.0, 1.0))
    engine = LapEngine(circuits=[circ], config=EngineConfig(min_lap_s=15.0, min_lap_dist=0.0))

    # Zwei Ueberquerungen kurz hintereinander (< 15 s) -> keine gewertete Runde.
    engine.update(0.0, pkt(50.0, -5.0))
    engine.update(1.0, pkt(50.0, 5.0))   # 1. Ueberquerung -> Start
    engine.update(2.0, pkt(50.0, -5.0))  # rueckwaerts (zaehlt nicht)
    ev = engine.update(5.0, pkt(50.0, 5.0))  # 2. Ueberquerung, nur 4 s
    assert ev is None
