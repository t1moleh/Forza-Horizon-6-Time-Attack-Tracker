"""Tests fuer die Linien-Ueberquerung (Kern der Mess-Logik)."""
import math

import pytest

from fh6tracker.gate import LineGate


def test_straight_crossing_interpolates_time_and_point():
    # Linie bei x=0, Fahrt in +x-Richtung. Zwischen den Paketen genau mittig.
    gate = LineGate(center=(0.0, 0.0), heading=(1.0, 0.0), half_width=2.5)
    c = gate.cross((-1.0, 0.0), 10.0, (1.0, 0.0), 12.0)
    assert c is not None
    assert c.fraction == pytest.approx(0.5)
    assert c.time == pytest.approx(11.0)          # mittig zwischen 10 und 12
    assert c.point[0] == pytest.approx(0.0)
    assert c.lateral == pytest.approx(0.0)


def test_crossing_not_at_midpoint():
    # Linie naeher an p0 -> kleiner Bruchteil, frueherer Zeitpunkt.
    gate = LineGate(center=(0.0, 0.0), heading=(1.0, 0.0))
    c = gate.cross((-1.0, 0.0), 0.0, (3.0, 0.0), 4.0)
    assert c is not None
    assert c.fraction == pytest.approx(0.25)
    assert c.time == pytest.approx(1.0)


def test_diagonal_crossing_within_width():
    # Schraege Anfahrt, Schnittpunkt seitlich aber innerhalb der 2.5 m.
    gate = LineGate(center=(0.0, 0.0), heading=(1.0, 0.0), half_width=2.5)
    c = gate.cross((-2.0, -2.0), 0.0, (2.0, 2.0), 1.0)
    assert c is not None
    assert c.point[0] == pytest.approx(0.0)
    assert c.lateral == pytest.approx(0.0)  # heading=+x -> perp=+z; bei x=0 ist z=0


def test_passes_outside_line_width_is_rejected():
    # Kreuzt die Linien-Ebene, aber 5 m seitlich -> ausserhalb half_width.
    gate = LineGate(center=(0.0, 0.0), heading=(1.0, 0.0), half_width=2.5)
    c = gate.cross((-1.0, 5.0), 0.0, (1.0, 5.0), 1.0)
    assert c is None


def test_backward_crossing_is_rejected():
    # Fahrt in -x-Richtung gegen heading=+x -> keine gueltige Ueberquerung.
    gate = LineGate(center=(0.0, 0.0), heading=(1.0, 0.0))
    c = gate.cross((1.0, 0.0), 0.0, (-1.0, 0.0), 1.0)
    assert c is None


def test_no_crossing_when_both_behind():
    gate = LineGate(center=(0.0, 0.0), heading=(1.0, 0.0))
    assert gate.cross((-3.0, 0.0), 0.0, (-1.0, 0.0), 1.0) is None


def test_no_crossing_when_both_ahead():
    gate = LineGate(center=(0.0, 0.0), heading=(1.0, 0.0))
    assert gate.cross((1.0, 0.0), 0.0, (3.0, 0.0), 1.0) is None


def test_sample_exactly_on_line_counts_as_start_of_next_segment():
    # p0 liegt exakt auf der Linie (d0==0): zaehlt als Ueberquerung bei f=0.
    gate = LineGate(center=(0.0, 0.0), heading=(1.0, 0.0))
    c = gate.cross((0.0, 0.0), 5.0, (2.0, 0.0), 6.0)
    assert c is not None
    assert c.fraction == pytest.approx(0.0)
    assert c.time == pytest.approx(5.0)


def test_endpoints_are_perpendicular_to_heading():
    gate = LineGate(center=(10.0, 20.0), heading=(0.0, 1.0), half_width=2.5)
    a, b = gate.endpoints()
    # heading=+z -> Linie laeuft entlang x; Enden bei x=10+-2.5, z=20.
    xs = sorted([a[0], b[0]])
    assert xs == pytest.approx([7.5, 12.5])
    assert a[1] == pytest.approx(20.0)
    assert b[1] == pytest.approx(20.0)


def test_zero_heading_rejected():
    with pytest.raises(ValueError):
        LineGate(center=(0.0, 0.0), heading=(0.0, 0.0))


def test_rotated_gate_time_interpolation():
    # 45-Grad-Linie, Fahrt quer hindurch; prueft, dass f/Zeit unabhaengig
    # von der Orientierung korrekt interpoliert werden.
    h = (math.cos(math.radians(45)), math.sin(math.radians(45)))
    gate = LineGate(center=(0.0, 0.0), heading=h, half_width=10.0)
    c = gate.cross((-1.0, -1.0), 100.0, (1.0, 1.0), 104.0)
    assert c is not None
    assert c.fraction == pytest.approx(0.5)
    assert c.time == pytest.approx(102.0)
