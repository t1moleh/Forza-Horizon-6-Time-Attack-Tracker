"""Tests fuer Session-Snapshot, Overall/Pro-Fahrzeug und Excel-Export."""
import csv
import os

from fh6tracker.engine import LapEvent
from fh6tracker.session import SessionState
from fh6tracker.snapshot import (build_by_car, build_overall, build_state,
                                 load_car_meta)
from fh6tracker.telemetry import Packet


def _write_log(path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["datum_uhrzeit", "auto", "car_ordinal", "klasse", "pi",
                    "antrieb", "rundenzeit_s", "rundenzeit", "strecke", "hinweis"])
        w.writerow(["2026-06-17 15:00:00", "Ferrari 355", "253", "A", "700", "RWD",
                    "92.500", "1:32.500", "Legend Island", "x"])
        w.writerow(["2026-06-17 15:05:00", "Ferrari 355", "253", "A", "700", "RWD",
                    "91.000", "1:31.000", "Legend Island", "x"])
        w.writerow(["2026-06-17 15:10:00", "Porsche 911", "3781", "S2", "886", "RWD",
                    "76.000", "1:16.000", "Legend Island", "x"])


def test_build_overall_ranks_per_track(tmp_path):
    log = str(tmp_path / "lap_times.csv")
    _write_log(log)
    overall = build_overall(log)
    # Beste je (Strecke, Auto): Ferrari 91.0, Porsche 76.0
    assert len(overall) == 2
    assert overall[0]["car_name"] == "Porsche 911"  # schneller -> Rang 1
    assert overall[0]["rank"] == 1
    assert overall[0]["time_seconds"] == 76.0
    assert overall[1]["rank"] == 2
    assert overall[1]["time_seconds"] == 91.0  # Ferrari-Bestzeit, nicht 92.5


def test_build_overall_enriches_year_type_country(tmp_path):
    log = str(tmp_path / "lap_times.csv")
    _write_log(log)
    meta_path = str(tmp_path / "car_meta.csv")
    with open(meta_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["car_ordinal", "car_name", "type", "country"])
        w.writerow(["253", "1994 Ferrari 355", "Retro Supercars", "Italy"])
        # Porsche (3781) absichtlich NICHT in den Metadaten -> leer, kein Fehler
    meta = load_car_meta(meta_path)
    overall = build_overall(log, meta)
    ferrari = next(e for e in overall if e["car_name"] == "Ferrari 355")
    porsche = next(e for e in overall if e["car_name"] == "Porsche 911")
    assert ferrari["type"] == "Retro Supercars"
    assert ferrari["country"] == "Italy"
    assert porsche["type"] == "" and porsche["country"] == ""   # Luecke -> leer
    # Jahr wird aus dem Namenspraefix gelesen (hier ohne Jahr -> leer)
    assert ferrari["year"] == ""


def test_build_overall_without_meta_has_empty_fields(tmp_path):
    log = str(tmp_path / "lap_times.csv")
    _write_log(log)
    for e in build_overall(log):           # kein meta -> Felder vorhanden, leer
        assert e["type"] == "" and e["country"] == ""
        assert "year" in e


def test_build_by_car_separates_tunings_by_pi(tmp_path):
    log = str(tmp_path / "lap_times.csv")
    with open(log, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["datum_uhrzeit", "auto", "car_ordinal", "klasse", "pi",
                    "antrieb", "rundenzeit_s", "rundenzeit", "strecke", "hinweis", "lap_id"])
        # Gleiches Modell, zwei Tunings (unterschiedliche PI/Klasse)
        w.writerow(["t", "Porsche 911 GT3 RS", "3781", "S2", "886", "RWD",
                    "75.0", "1:15.000", "Legend Island", "x", ""])
        w.writerow(["t", "Porsche 911 GT3 RS", "3781", "A", "800", "RWD",
                    "79.0", "1:19.000", "Legend Island", "x", ""])
    by_car = build_by_car(log)
    assert len(by_car) == 2                       # zwei Varianten statt einer
    pis = sorted(c["pi"] for c in by_car)
    assert pis == [800, 886]
    # staerkste Variante zuerst
    assert by_car[0]["pi"] == 886


def test_build_by_car_groups_and_sorts(tmp_path):
    log = str(tmp_path / "lap_times.csv")
    _write_log(log)
    by_car = build_by_car(log)
    ferrari = next(c for c in by_car if c["name"] == "Ferrari 355")
    assert ferrari["lap_count"] == 2
    assert ferrari["best"] == "1:31.000"
    assert ferrari["laps"][0]["time_seconds"] == 91.0  # sortiert: schnellste zuerst


def test_session_snapshot_tracks_laps_and_best():
    sess = SessionState()

    def names(o):
        return {253: "Ferrari 355"}.get(o, f"Car #{o}")

    pkt = Packet(race_on=1, ordinal=253, car_class=3, pi=700, drivetrain=1,
                 x=0.0, z=0.0)
    sess.note_packet(pkt, names)
    sess.add_lap(LapEvent(92.5, 100.0, "Legend Island", pkt, approximate=False), "Ferrari 355")
    sess.add_lap(LapEvent(91.0, 200.0, "Legend Island", pkt, approximate=False), "Ferrari 355")

    snap = sess.snapshot()
    assert snap["lap_count"] == 2
    assert snap["session_best"]["time_seconds"] == 91.0
    assert snap["current_car"]["name"] == "Ferrari 355"
    assert len(snap["cars_used"]) == 1
    assert snap["cars_used"][0]["lap_count"] == 2
    assert snap["cars_used"][0]["car_name"] == "Ferrari 355"


def test_class_names_fh6_r_and_x():
    # FH6: CarClass 6 = R (unter X), 7 = X. Frueher beide faelschlich X.
    assert Packet(1, 100, 6, 924, 1, 0.0, 0.0).class_name == "R"
    assert Packet(1, 100, 7, 999, 1, 0.0, 0.0).class_name == "X"
    assert Packet(1, 100, 5, 886, 1, 0.0, 0.0).class_name == "S2"


def test_cars_used_excludes_cars_without_laps():
    sess = SessionState()
    a = Packet(1, 253, 3, 700, 1, 0.0, 0.0)        # Auto A: faehrt eine Runde
    sess.note_packet(a, lambda o: "Ferrari")
    sess.add_lap(LapEvent(92.0, 100.0, "T", a, approximate=False), "Ferrari")
    b = Packet(1, 999, 5, 886, 1, 0.0, 0.0)        # Auto B: nur reingespawnt
    sess.note_packet(b, lambda o: "Audi")          # keine Runde
    names = [c["car_name"] for c in sess.snapshot()["cars_used"]]
    assert "Ferrari" in names
    assert "Audi" not in names                     # ohne gueltige Runde -> nicht gelistet


def test_approximate_laps_excluded_from_best():
    sess = SessionState()
    pkt = Packet(1, 253, 3, 700, 1, 0.0, 0.0)
    sess.note_packet(pkt, lambda o: "Car")
    sess.add_lap(LapEvent(80.0, 1.0, "T", pkt, approximate=True), "Car")  # Schaetzung
    sess.add_lap(LapEvent(95.0, 2.0, "T", pkt, approximate=False), "Car")
    snap = sess.snapshot()
    assert snap["session_best"]["time_seconds"] == 95.0  # 80er Schaetzung zaehlt nicht


def test_build_state_shape(tmp_path):
    log = str(tmp_path / "lap_times.csv")
    _write_log(log)
    state = build_state(SessionState(), log)
    # verschachtelt + Top-Level-Schluessel fuer die Design-UI
    assert {"connected", "in_world", "session", "overall", "by_car"} <= set(state)
    for k in ("current_car", "session_best", "last_laps", "cars_used", "current_lap"):
        assert k in state, f"Top-Level-Feld fehlt: {k}"


def test_excel_export_creates_file(tmp_path):
    log = str(tmp_path / "lap_times.csv")
    _write_log(log)
    out = str(tmp_path / "out.xlsx")
    from fh6tracker.excel_export import export_excel
    export_excel(log, out)
    assert os.path.exists(out) and os.path.getsize(out) > 0
