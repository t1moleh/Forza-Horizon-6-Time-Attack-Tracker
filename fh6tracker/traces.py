"""Speicherung der Telemetrie-Spur je Runde (eine JSON-Datei pro Runde).

Spaltenweises Format (klein, leicht zu zeichnen):
    {
      "lap_id", "car_name", "car_ordinal", "track",
      "time_seconds", "time",
      "channels": { "dist":[], "t":[], "speed_kmh":[], "throttle":[],
                    "brake":[], "gear":[], "rpm":[], "steer":[],
                    "g_lat":[], "g_long":[],
                    "slip_fl":[], "slip_fr":[], "slip_rl":[], "slip_rr":[] }
    }
"""
from __future__ import annotations

import csv
import json
import os

CHANNELS = ["dist", "t", "speed_kmh", "throttle", "brake", "gear", "rpm",
            "steer", "g_lat", "g_long", "slip_fl", "slip_fr", "slip_rl", "slip_rr"]


def empty_channels() -> dict:
    return {k: [] for k in CHANNELS}


def sample_from(lap_dist: float, elapsed: float, telem: dict) -> dict:
    """Baut einen Spur-Punkt aus lap_dist/elapsed + Live-Telemetrie-Dict."""
    slip = telem.get("tire_slip", {}) or {}
    return {
        "dist": round(lap_dist, 1), "t": round(elapsed, 3),
        "speed_kmh": telem.get("speed_kmh", 0.0),
        "throttle": telem.get("throttle", 0), "brake": telem.get("brake", 0),
        "gear": telem.get("gear", 0), "rpm": telem.get("rpm", 0),
        "steer": telem.get("steer", 0),
        "g_lat": telem.get("accel_lat_g", 0.0), "g_long": telem.get("accel_long_g", 0.0),
        "slip_fl": slip.get("fl", 0.0), "slip_fr": slip.get("fr", 0.0),
        "slip_rl": slip.get("rl", 0.0), "slip_rr": slip.get("rr", 0.0),
    }


def append_sample(channels: dict, sample: dict) -> None:
    for k in CHANNELS:
        channels[k].append(sample.get(k, 0))


def save_trace(traces_dir: str, trace: dict) -> str:
    os.makedirs(traces_dir, exist_ok=True)
    path = os.path.join(traces_dir, f"{trace['lap_id']}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(trace, fh, separators=(",", ":"))
    return path


def load_trace(traces_dir: str, lap_id: str) -> dict | None:
    path = os.path.join(traces_dir, f"{lap_id}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def best_lap_id_for(log_path: str, car: str, track: str,
                    exclude_id: str | None = None) -> str | None:
    """lap_id der schnellsten Runde dieser (Auto, Strecke)-Kombi aus dem Log."""
    best_id, best_t = None, float("inf")
    if not os.path.exists(log_path):
        return None
    with open(log_path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("auto") != car or r.get("strecke") != track:
                continue
            lap_id = r.get("lap_id")
            if not lap_id or lap_id == exclude_id:
                continue
            try:
                t = float(r["rundenzeit_s"])
            except (ValueError, KeyError):
                continue
            if t < best_t:
                best_id, best_t = lap_id, t
    return best_id
