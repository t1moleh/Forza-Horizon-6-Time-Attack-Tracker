"""Tests fuer das 'persoenliche Bestzeit'-Signal (is_record) - Basis fuer den
Bestzeit-Ton in der UI."""
import csv

from fh6tracker.engine import LapEvent
from fh6tracker.session import SessionState
from fh6tracker.storage import LOG_HEADER, is_personal_best
from fh6tracker.telemetry import Packet


def _log(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(LOG_HEADER)
        for car, track, sec in rows:
            w.writerow(["t", car, "253", "A", "700", "RWD", f"{sec:.3f}", "x",
                        track, "x", ""])


def test_is_personal_best_against_log(tmp_path):
    log = str(tmp_path / "lap_times.csv")
    _log(log, [("Ferrari", "Legend Island", 92.0)])
    assert is_personal_best(log, "Ferrari", "Legend Island", 91.0) is True   # schneller
    assert is_personal_best(log, "Ferrari", "Legend Island", 93.0) is False  # langsamer
    # gleiches Auto andere Strecke -> noch kein Eintrag -> Rekord
    assert is_personal_best(log, "Ferrari", "Hokubu", 99.0) is True
    # anderes Auto -> noch kein Eintrag -> Rekord
    assert is_personal_best(log, "Porsche", "Legend Island", 95.0) is True


def test_is_personal_best_empty_log(tmp_path):
    log = str(tmp_path / "missing.csv")
    assert is_personal_best(log, "Ferrari", "Legend Island", 90.0) is True


def test_snapshot_exposes_is_record():
    sess = SessionState()
    pkt = Packet(1, 253, 3, 700, 1, 0.0, 0.0)
    sess.note_packet(pkt, lambda o: "Ferrari")
    sess.add_lap(LapEvent(92.0, 1.0, "Legend Island", pkt, approximate=False),
                 "Ferrari", is_record=True)
    snap = sess.snapshot()
    assert snap["last_laps"][0]["is_record"] is True
    assert snap["last_laps"][0]["is_best"] is True
