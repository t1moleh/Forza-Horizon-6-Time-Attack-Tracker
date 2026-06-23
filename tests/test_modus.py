"""Tests fuer den modus (timeattack/rivals): Migration, Trennung im Overall."""
import csv

from fh6tracker.snapshot import build_overall
from fh6tracker.storage import LOG_HEADER, ensure_log, log_lap
from fh6tracker.engine import LapEvent
from fh6tracker.telemetry import Packet


def test_ensure_log_adds_modus_to_old_rows(tmp_path):
    log = tmp_path / "lap_times.csv"
    old_header = [c for c in LOG_HEADER if c != "modus"]      # v0.2.x ohne modus
    with open(log, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(old_header)
        w.writerow(["t", "Ferrari", "253", "A", "700", "RWD",
                    "90.0", "1:30", "X", "h", "1"])
    ensure_log(str(log))
    with open(log, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert "modus" in rows[0]
    assert rows[0]["modus"] == "timeattack"                   # Bestand -> timeattack


def test_log_lap_writes_rivals_modus(tmp_path):
    log = tmp_path / "lap_times.csv"
    ensure_log(str(log))
    pkt = Packet(1, 253, 3, 700, 1, 0.0, 0.0)
    ev = LapEvent(80.0, 1.0, "Airfield Trail", pkt, approximate=False)
    log_lap(str(log), ev, "Ferrari", "lap1", modus="rivals")
    with open(log, newline="", encoding="utf-8") as fh:
        row = list(csv.DictReader(fh))[0]
    assert row["modus"] == "rivals"
    assert "Rivals" in row["hinweis"]


def test_build_overall_separates_modes(tmp_path):
    log = tmp_path / "lap_times.csv"
    with open(log, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(LOG_HEADER)
        w.writerow(["t", "Ferrari", "253", "A", "700", "RWD",
                    "90.0", "1:30", "X", "h", "1", "timeattack"])
        w.writerow(["t", "Ferrari", "253", "A", "700", "RWD",
                    "80.0", "1:20", "X", "h", "2", "rivals"])
    ov = build_overall(str(log))
    assert len(ov) == 2                                       # 2 Modi, nicht gemischt
    assert sorted(e["modus"] for e in ov) == ["rivals", "timeattack"]
    assert all(e["rank"] == 1 for e in ov)                   # je Modus eigener Rang 1
