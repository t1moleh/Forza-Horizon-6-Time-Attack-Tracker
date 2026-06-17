"""Test fuer die Migration alter lap_times.csv (Kopfzeile ohne lap_id)."""
import csv

from fh6tracker.storage import ensure_log


def test_migrate_old_header_recovers_lap_id(tmp_path):
    log = str(tmp_path / "lap_times.csv")
    # Alte 10-Spalten-Kopfzeile; eine Zeile hat bereits eine 11. Spalte (lap_id)
    with open(log, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["datum_uhrzeit", "auto", "car_ordinal", "klasse", "pi",
                    "antrieb", "rundenzeit_s", "rundenzeit", "strecke", "hinweis"])
        w.writerow(["t", "Auto A", "1", "A", "700", "RWD", "90.0", "1:30.000",
                    "S", "x"])  # 10 Spalten -> kein lap_id
        w.writerow(["t", "Auto A", "1", "A", "700", "RWD", "89.0", "1:29.000",
                    "S", "x", "LAP_42"])  # 11 Spalten -> lap_id in Extra-Spalte

    ensure_log(log)  # migriert

    rows = list(csv.DictReader(open(log, newline="", encoding="utf-8")))
    assert "lap_id" in rows[0]
    # alte Zeile ohne ID -> wird mit synthetischer ID aufgefuellt (loeschbar)
    assert rows[0]["lap_id"] and rows[0]["lap_id"] != "LAP_42"
    assert rows[1]["lap_id"] == "LAP_42"  # 11. Spalte gerettet
    # idempotent: zweiter Aufruf aendert nichts
    ensure_log(log)
    rows2 = list(csv.DictReader(open(log, newline="", encoding="utf-8")))
    assert rows2[1]["lap_id"] == "LAP_42"
