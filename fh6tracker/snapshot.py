"""Baut den vollstaendigen JSON-Zustand (Daten-Vertrag) fuer UI/Excel.

Quelle der Wahrheit fuer historische Zeiten ist lap_times.csv; der
Session-Teil kommt live aus SessionState. Genau diese Struktur konsumiert
das Web-Dashboard (fetch /api/state) - die in Claude Design entworfene UI
sollte dieselben Feldnamen verwenden.
"""
from __future__ import annotations

import csv
import os
import re

from .session import SessionState
from .util import fmt_time

# Fahrzeug-Metadaten (Typ/Division + Land je Auto, Quelle forza.net/fh6cars).
# Cache nach (Pfad, mtime), damit manuelles Nachpflegen ohne Neustart greift.
_meta_cache: dict[str, tuple[float, dict]] = {}


def load_car_meta(path: str | None) -> dict[int, dict]:
    """car_meta.csv -> {ordinal: {"type":..., "country":...}}. Leer bei Fehlen."""
    if not path or not os.path.exists(path):
        return {}
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    hit = _meta_cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    meta: dict[int, dict] = {}
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                o = (r.get("car_ordinal") or "").strip()
                if o.lstrip("-").isdigit():
                    meta[int(o)] = {
                        "type": (r.get("type") or "").strip(),
                        "country": (r.get("country") or "").strip(),
                    }
    except OSError:
        return {}
    _meta_cache[path] = (mtime, meta)
    return meta


def _year_of(name: str) -> str:
    m = re.match(r"\s*(\d{4})", name or "")
    return m.group(1) if m else ""


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


def build_overall(log_path: str, meta: dict[int, dict] | None = None) -> list[dict]:
    """Beste Zeit je (Strecke, Auto), sortiert nach Strecke dann Zeit.

    meta (optional): {ordinal: {type, country}} aus car_meta.csv - haengt
    Fahrzeugtyp/Land je Eintrag an (fuer die Filter im Overall-Tab).
    """
    meta = meta or {}
    best: dict[tuple[str, str, str], dict] = {}
    for r in _read_laps(log_path):
        modus = r.get("modus") or "timeattack"
        key = (r["strecke"], r["auto"], modus)
        if key not in best or r["_sec"] < best[key]["_sec"]:
            best[key] = r
    out = []
    for (track, car, modus), r in best.items():
        ordn = (r.get("car_ordinal") or "").strip()
        m = meta.get(int(ordn)) if ordn.lstrip("-").isdigit() else None
        out.append({
            "track": track, "car_name": car, "class": r["klasse"],
            "pi": int(r["pi"]) if r["pi"].isdigit() else r["pi"],
            "drivetrain": r["antrieb"],
            "time": fmt_time(r["_sec"]), "time_seconds": round(r["_sec"], 3),
            "year": _year_of(car),
            "type": (m or {}).get("type", ""),
            "country": (m or {}).get("country", ""),
            "modus": modus,
        })
    out.sort(key=lambda e: (e["track"], e["time_seconds"]))
    # Rang je (Strecke, Modus) - Time Attack und Rivals getrennt
    rank: dict[tuple[str, str], int] = {}
    for e in out:
        k = (e["track"], e["modus"])
        rank[k] = rank.get(k, 0) + 1
        e["rank"] = rank[k]
    return out


def build_by_car(log_path: str, traces_dir: str | None = None) -> list[dict]:
    """Alle Zeiten je Fahrzeug-Variante (Modell + Klasse + PI), nach Zeit sortiert.

    Die Telemetrie kennt keine Tuning-Identitaet, aber Tuning aendert fast immer
    die PI - daher werden Varianten ueber (Modell, Klasse, PI) getrennt. Gleiches
    Modell mit identischem Tuning faellt korrekt zusammen.
    """
    cars: dict[tuple, dict] = {}
    for r in _read_laps(log_path):
        modus = r.get("modus") or "timeattack"
        key = (r["auto"], r["klasse"], r["pi"], modus)
        entry = cars.setdefault(key, {
            "ordinal": int(r["car_ordinal"]) if r["car_ordinal"].lstrip("-").isdigit() else None,
            "name": r["auto"], "class": r["klasse"],
            "pi": int(r["pi"]) if r["pi"].isdigit() else r["pi"],
            "drivetrain": r["antrieb"], "modus": modus, "laps": [],
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
                traces_dir: str | None = None,
                meta_path: str | None = None) -> dict:
    sess = session.snapshot()
    meta = load_car_meta(meta_path)
    state = {
        "connected": session.connected,
        "in_world": session.in_world,
        "session": sess,  # verschachtelt (interne Nutzung/Tests)
        "overall": build_overall(log_path, meta),
        "by_car": build_by_car(log_path, traces_dir),
    }
    # Session-Felder zusaetzlich flach auf oberster Ebene: die in Claude Design
    # entworfene UI liest current_car/session_best/last_laps/... direkt von s.*
    state.update(sess)
    return state
