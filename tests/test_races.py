"""Tests fuer die Strecken-/Event-Registry (races.csv) + Positions-Erkennung."""
import csv
import os

from fh6tracker import races as rc

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_load_and_nearest(tmp_path):
    p = tmp_path / "races.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["slug", "name", "category", "type", "x", "y", "z"])
        w.writerow(["a", "Airfield Trail", "races", "rally_race", "909.9", "119", "-1128.0"])
        w.writerow(["b", "Far Away", "races", "road_race", "5000.0", "0", "5000.0"])
    races = rc.load_races(str(p))
    assert len(races) == 2
    near = rc.nearest_race(races, 920.0, -1130.0)         # nah an Airfield Trail
    assert near is not None and near.name == "Airfield Trail"
    assert rc.nearest_race(races, 0.0, 0.0) is None        # zu weit von allem


def test_bundled_races_csv_has_time_attack_circuits():
    # Die gebuendelte races.csv enthaelt die 4 Time-Attack-Circuits passend
    # zu circuits.csv (verifiziert das Koordinatensystem).
    races = rc.load_races(os.path.join(PROJECT, "races.csv"))
    assert len(races) > 100
    ta = [r for r in races if r.type == "time_attack"]
    assert len(ta) >= 4
    # Legend Island liegt bei ~(4267,-5273) laut circuits.csv
    near = rc.nearest_race(races, 4267.6, -5273.1, max_dist=50.0)
    assert near is not None and "Legend Island" in near.name
