"""Persistenz: Auto-Namen, Runden-Log (lap_times.csv), Bestzeiten.

Bewusst schlank gehalten; der schoen formatierte Excel-Export kommt in
Baustein 3 dazu und liest dieselben CSVs.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime

from .engine import LapEvent
from .util import fmt_time

LOG_HEADER = [
    "datum_uhrzeit", "auto", "car_ordinal", "klasse", "pi", "antrieb",
    "rundenzeit_s", "rundenzeit", "strecke", "hinweis", "lap_id",
]
BEST_HEADER = [
    "strecke", "auto", "klasse", "pi", "antrieb", "beste_rundenzeit", "rundenzeit_s",
]


class NameStore:
    """CarOrdinal -> Fahrzeugname (car_names.csv); unbekannte werden ergaenzt."""

    def __init__(self, path: str):
        self.path = path
        self.names: dict[int, str] = {}
        if os.path.exists(path):
            with open(path, newline="", encoding="utf-8") as fh:
                for row in csv.reader(fh):
                    if len(row) >= 2 and row[0].lstrip("-").isdigit():
                        self.names[int(row[0])] = row[1].strip()
        else:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerow(["car_ordinal", "car_name"])

    def display(self, ordinal: int) -> str:
        if ordinal not in self.names:
            self.names[ordinal] = ""
            with open(self.path, "a", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerow([ordinal, ""])
        return self.names[ordinal] or f"Car #{ordinal}"


def ensure_log(path: str) -> None:
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow(LOG_HEADER)
        return
    _migrate_log(path)
    _ensure_lap_ids(path)


def _ensure_lap_ids(path: str) -> None:
    """Jede Runde braucht eine eindeutige lap_id (fuer Loeschen/Referenz).
    Leere IDs (alte/Schaetz-Runden) werden stabil aufgefuellt."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    if not rows or "lap_id" not in rows[0]:
        return
    idx = rows[0].index("lap_id")
    try:
        oi = rows[0].index("car_ordinal")
    except ValueError:
        oi = -1
    changed = False
    for i, r in enumerate(rows[1:], 1):
        if len(r) > idx and not r[idx]:
            ordn = r[oi] if 0 <= oi < len(r) else "0"
            r[idx] = f"legacy_{i:05d}_{ordn}"
            changed = True
    if changed:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(rows)


def delete_lap(log_path: str, lap_id: str, traces_dir: str | None = None,
               best_path: str | None = None) -> bool:
    """Loescht die Runde mit dieser lap_id aus dem Log (+ Spur-Datei), und
    baut die Bestzeiten neu. Gibt True zurueck, wenn etwas geloescht wurde."""
    if not lap_id or not os.path.exists(log_path):
        return False
    with open(log_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    if not rows or "lap_id" not in rows[0]:
        return False
    idx = rows[0].index("lap_id")
    kept = [rows[0]]
    removed = 0
    for r in rows[1:]:
        if len(r) > idx and r[idx] == lap_id:
            removed += 1
            continue
        kept.append(r)
    if not removed:
        return False
    with open(log_path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(kept)
    if traces_dir:
        trace = os.path.join(traces_dir, f"{lap_id}.json")
        if os.path.isfile(trace):
            os.remove(trace)
    if best_path:
        rebuild_bestlaps(log_path, best_path)
    return True


def is_personal_best(log_path: str, car: str, track: str, lap_seconds: float) -> bool:
    """True, wenn lap_seconds schneller ist als jede bisher geloggte Zeit dieser
    (Auto, Strecke)-Kombi (all-time persoenliche Bestzeit). Vor dem Loggen der
    neuen Runde aufrufen."""
    best = None
    if os.path.exists(log_path):
        with open(log_path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r.get("auto") != car or r.get("strecke") != track:
                    continue
                try:
                    t = float(r["rundenzeit_s"])
                except (ValueError, KeyError):
                    continue
                if best is None or t < best:
                    best = t
    return best is None or lap_seconds < best


def _migrate_log(path: str) -> None:
    """Hebt eine alte Kopfzeile (ohne lap_id) auf das aktuelle Format an.

    Aeltere Versionen schrieben 10 Spalten; spaetere haengten die lap_id als
    unbenannte 11. Spalte an. Hier wird die Kopfzeile ergaenzt - dadurch werden
    bereits aufgezeichnete Spuren wieder mit ihren Runden verknuepft.
    """
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    if not rows or rows[0] == LOG_HEADER:
        return
    if "lap_id" in rows[0]:
        return
    n = len(LOG_HEADER)
    fixed = [LOG_HEADER]
    for r in rows[1:]:
        if len(r) >= n:
            fixed.append(r[:n])              # 11. Spalte = lap_id (uebernehmen)
        else:
            fixed.append(r + [""] * (n - len(r)))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(fixed)


def log_lap(path: str, ev: LapEvent, auto: str, lap_id: str = "") -> None:
    pkt = ev.car
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hinweis = "Tool-Stoppuhr (Time Attack)"
    if ev.approximate:
        hinweis += " - erste Runde (Schaetzung)"
    with open(path, "a", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow([
            stamp, auto, pkt.ordinal, pkt.class_name, pkt.pi, pkt.drivetrain_name,
            f"{ev.lap_time:.3f}", fmt_time(ev.lap_time), ev.circuit, hinweis, lap_id,
        ])


def rebuild_bestlaps(log_path: str, best_path: str) -> list:
    """Beste Zeit je (Auto, Strecke) aus dem Log neu berechnen und schreiben."""
    best: dict[tuple[str, str], tuple[float, dict]] = {}
    if not os.path.exists(log_path):
        return []
    with open(log_path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                tsec = float(r["rundenzeit_s"])
            except (ValueError, KeyError):
                continue
            key = (r["auto"], r["strecke"])
            if key not in best or tsec < best[key][0]:
                best[key] = (tsec, r)
    rows = sorted(best.items(), key=lambda kv: (kv[0][1], kv[1][0]))
    with open(best_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(BEST_HEADER)
        for (auto, strecke), (tsec, r) in rows:
            w.writerow([strecke, auto, r["klasse"], r["pi"], r["antrieb"],
                        fmt_time(tsec), f"{tsec:.3f}"])
    return rows
