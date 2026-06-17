"""Baut den vollstaendigen JSON-Zustand (Daten-Vertrag) fuer UI/Excel.

Quelle der Wahrheit fuer historische Zeiten ist lap_times.csv; der
Session-Teil kommt live aus SessionState. Genau diese Struktur konsumiert
das Web-Dashboard (fetch /api/state) - die in Claude Design entworfene UI
sollte dieselben Feldnamen verwenden.
"""
from __future__ import annotations

import csv
import os

from .session import SessionState
from .util import fmt_time


def _read_laps(log_path: str) -> list[dict]:
    rows = []
    if not os.path.exists(log_path):
        return rows
    with open(log_path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                r["_sec"] = float(r["rundenzeit_s"])
            except (ValueError, KeyError):
                continue
            rows.append(r)
    return rows


def build_overall(log_path: str) -> list[dict]:
    """Beste Zeit je (Strecke, Auto), sortiert nach Strecke dann Zeit."""
    best: dict[tuple[str, str], dict] = {}
    for r in _read_laps(log_path):
        key = (r["strecke"], r["auto"])
        if key not in best or r["_sec"] < best[key]["_sec"]:
            best[key] = r
    out = []
    for (track, car), r in best.items():
        out.append({
            "track": track, "car_name": car, "class": r["klasse"],
            "pi": int(r["pi"]) if r["pi"].isdigit() else r["pi"],
            "drivetrain": r["antrieb"],
            "time": fmt_time(r["_sec"]), "time_seconds": round(r["_sec"], 3),
        })
    out.sort(key=lambda e: (e["track"], e["time_seconds"]))
    # Rang je Strecke
    rank: dict[str, int] = {}
    for e in out:
        rank[e["track"]] = rank.get(e["track"], 0) + 1
        e["rank"] = rank[e["track"]]
    return out


def build_by_car(log_path: str, traces_dir: str | None = None) -> list[dict]:
    """Alle Zeiten je Fahrzeug-Variante (Modell + Klasse + PI), nach Zeit sortiert.

    Die Telemetrie kennt keine Tuning-Identitaet, aber Tuning aendert fast immer
    die PI - daher werden Varianten ueber (Modell, Klasse, PI) getrennt. Gleiches
    Modell mit identischem Tuning faellt korrekt zusammen.
    """
    cars: dict[tuple, dict] = {}
    for r in _read_laps(log_path):
        key = (r["auto"], r["klasse"], r["pi"])
        entry = cars.setdefault(key, {
            "ordinal": int(r["car_ordinal"]) if r["car_ordinal"].lstrip("-").isdigit() else None,
            "name": r["auto"], "class": r["klasse"],
            "pi": int(r["pi"]) if r["pi"].isdigit() else r["pi"],
            "drivetrain": r["antrieb"], "laps": [],
        })
        lap_id = r.get("lap_id", "")
        if traces_dir is not None:
            has_tele = bool(lap_id) and os.path.isfile(
                os.path.join(traces_dir, f"{lap_id}.json"))
        else:
            has_tele = bool(lap_id)
        entry["laps"].append({
            "track": r["strecke"], "time": fmt_time(r["_sec"]),
            "time_seconds": round(r["_sec"], 3), "timestamp": r["datum_uhrzeit"],
            "lap_id": lap_id,
            "has_telemetry": has_tele,
        })
    for entry in cars.values():
        entry["laps"].sort(key=lambda lp: lp["time_seconds"])
        entry["best"] = entry["laps"][0]["time"] if entry["laps"] else None
        entry["lap_count"] = len(entry["laps"])
    # gleiche Modelle beieinander, staerkste Variante (hoechste PI) zuerst
    return sorted(cars.values(),
                  key=lambda c: (c["name"], -(c["pi"] if isinstance(c["pi"], int) else 0)))


def build_state(session: SessionState, log_path: str,
                traces_dir: str | None = None) -> dict:
    sess = session.snapshot()
    state = {
        "connected": session.connected,
        "in_world": session.in_world,
        "session": sess,  # verschachtelt (interne Nutzung/Tests)
        "overall": build_overall(log_path),
        "by_car": build_by_car(log_path, traces_dir),
    }
    # Session-Felder zusaetzlich flach auf oberster Ebene: die in Claude Design
    # entworfene UI liest current_car/session_best/last_laps/... direkt von s.*
    state.update(sess)
    return state
