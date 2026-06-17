"""Tests fuer Runden loeschen + lap_id-Vergabe + has_telemetry via Spur."""
import csv
import os

from fh6tracker import traces as tr
from fh6tracker.snapshot import build_by_car
from fh6tracker.storage import LOG_HEADER, delete_lap, ensure_log


def _write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(LOG_HEADER)
        for r in rows:
            w.writerow(r)


def _row(auto, sec, lap_id, ordinal="253"):
    return ["2026-06-17 15:00:00", auto, ordinal, "A", "700", "RWD",
            f"{sec:.3f}", "x", "Track", "x", lap_id]


def test_ensure_lap_ids_fills_empty(tmp_path):
    log = str(tmp_path / "lap_times.csv")
    _write(log, [_row("A", 90.0, ""), _row("A", 91.0, "KEEP")])
    ensure_log(log)
    rows = list(csv.DictReader(open(log, newline="", encoding="utf-8")))
    assert rows[0]["lap_id"]               # leere ID aufgefuellt
    assert rows[1]["lap_id"] == "KEEP"     # vorhandene bleibt
    assert rows[0]["lap_id"] != rows[1]["lap_id"]


def test_delete_lap_removes_row_and_trace(tmp_path):
    log = str(tmp_path / "lap_times.csv")
    tdir = str(tmp_path / "laps")
    best = str(tmp_path / "best.csv")
    _write(log, [_row("A", 90.0, "L1"), _row("A", 91.0, "L2")])
    tr.save_trace(tdir, {"lap_id": "L1", "car_name": "A", "track": "Track",
                         "time_seconds": 90.0, "time": "x",
                         "channels": tr.empty_channels()})
    assert os.path.isfile(os.path.join(tdir, "L1.json"))

    assert delete_lap(log, "L1", tdir, best) is True
    rows = list(csv.DictReader(open(log, newline="", encoding="utf-8")))
    assert [r["lap_id"] for r in rows] == ["L2"]          # L1 weg
    assert not os.path.isfile(os.path.join(tdir, "L1.json"))  # Spur weg
    # unbekannte ID -> nichts geloescht
    assert delete_lap(log, "nope", tdir, best) is False


def test_has_telemetry_uses_trace_existence(tmp_path):
    log = str(tmp_path / "lap_times.csv")
    tdir = str(tmp_path / "laps")
    _write(log, [_row("A", 90.0, "L1"), _row("A", 91.0, "L2")])
    tr.save_trace(tdir, {"lap_id": "L1", "channels": tr.empty_channels()})
    by_car = build_by_car(log, traces_dir=tdir)
    laps = {lp["lap_id"]: lp["has_telemetry"] for c in by_car for lp in c["laps"]}
    assert laps["L1"] is True    # Spur existiert
    assert laps["L2"] is False   # ID vorhanden, aber keine Spur
