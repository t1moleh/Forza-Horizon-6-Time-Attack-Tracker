"""Strecken-/Event-Registry aus der labs.gg-Karte (races.csv): Name + Welt-
Koordinaten je Rennen/Event in FH6. Dient der Erkennung der aktuellen Strecke
ueber die Fahrzeugposition - vor allem fuer den Rivals-Modus, wo die Zeit aus
dem Spiel kommt, aber die Strecke ueber die Position bestimmt wird.

Die Koordinaten stammen aus telemetrie-kalibrierten labs.gg-Daten und decken
sich mit dem FH6 "Data Out"-Positionssystem (verifiziert: die 4 Time-Attack-
Circuits stimmen mit unserer circuits.csv auf wenige Meter ueberein).
"""
from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass

# Renntypen mit klassischer Runden-Logik (relevant fuer die Rivals-Rundenzeit).
LAP_TYPES = frozenset({"road_race", "street_race", "rally_race",
                       "cross_country_race", "touge_race", "circuit_race",
                       "time_attack", "drag_race"})


@dataclass(frozen=True)
class Race:
    slug: str
    name: str
    category: str
    type: str
    x: float
    z: float


def load_races(path: str) -> list[Race]:
    """races.csv -> Liste von Race. Leer bei Fehlen/Fehler."""
    out: list[Race] = []
    if not path or not os.path.exists(path):
        return out
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try:
                    out.append(Race(
                        r.get("slug", ""), r.get("name", ""),
                        r.get("category", ""), r.get("type", ""),
                        float(r["x"]), float(r["z"])))
                except (ValueError, KeyError):
                    continue
    except OSError:
        return []
    return out


def nearest_race(races: list[Race], x: float, z: float,
                 max_dist: float = 150.0) -> Race | None:
    """Naechstes Rennen/Event zur Position (x, z), wenn innerhalb max_dist (m).
    Sonst None. (Renn-Marker liegen ~wenige Meter von der Startlinie entfernt.)"""
    best: Race | None = None
    best_d = max_dist
    for r in races:
        d = math.hypot(x - r.x, z - r.z)
        if d < best_d:
            best, best_d = r, d
    return best
