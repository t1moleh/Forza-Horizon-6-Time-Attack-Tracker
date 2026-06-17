"""Tests fuer den Ghost-Vergleich (Live-Delta) und Bestzeit-Markierung."""
import pytest

from fh6tracker.ghost import GhostComparer
from fh6tracker.engine import LapEvent
from fh6tracker.session import SessionState
from fh6tracker.telemetry import Packet


def _profile(speed_mps, lap_seconds, step=10.0):
    """Gleichfoermiges Profil: (lap_dist, elapsed) bei konstantem Tempo."""
    prof = []
    d = 0.0
    while d <= speed_mps * lap_seconds:
        prof.append((d, d / speed_mps))
        d += step
    return tuple(prof)


def test_consider_accepts_first_and_faster_only():
    g = GhostComparer()
    assert g.consider(253, "T", 92.0, _profile(20, 92)) is True
    assert g.has_reference(253, "T")
    # langsamer -> keine neue Referenz
    assert g.consider(253, "T", 95.0, _profile(20, 95)) is False
    # schneller -> neue Referenz
    assert g.consider(253, "T", 90.0, _profile(20, 90)) is True


def test_delta_zero_against_same_pace():
    g = GhostComparer()
    g.consider(253, "T", 100.0, _profile(20, 100))
    # bei 400 m und gleichem Tempo: elapsed 20 s == Referenz -> Delta 0
    assert g.delta(253, "T", 400.0, 20.0) == pytest.approx(0.0, abs=0.01)


def test_delta_positive_when_slower():
    g = GhostComparer()
    g.consider(253, "T", 100.0, _profile(20, 100))
    # bei 400 m, aber 22 s gebraucht -> 2 s langsamer
    assert g.delta(253, "T", 400.0, 22.0) == pytest.approx(2.0, abs=0.01)


def test_delta_negative_when_faster():
    g = GhostComparer()
    g.consider(253, "T", 100.0, _profile(20, 100))
    assert g.delta(253, "T", 400.0, 18.5) == pytest.approx(-1.5, abs=0.01)


def test_delta_none_without_reference():
    g = GhostComparer()
    assert g.delta(999, "X", 100.0, 10.0) is None


def test_session_marks_new_best():
    sess = SessionState()
    pkt = Packet(1, 253, 3, 700, 1, 0.0, 0.0)
    sess.note_packet(pkt, lambda o: "Car")
    assert sess.add_lap(LapEvent(95.0, 1.0, "T", pkt, approximate=False), "Car") is True
    assert sess.add_lap(LapEvent(96.0, 2.0, "T", pkt, approximate=False), "Car") is False
    assert sess.add_lap(LapEvent(93.0, 3.0, "T", pkt, approximate=False), "Car") is True
    snap = sess.snapshot()
    # juengste zuerst: 93.0 ist neue Bestzeit
    assert snap["last_laps"][0]["is_best"] is True
