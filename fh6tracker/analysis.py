"""Rundenanalyse: wertet die aufgezeichnete Telemetrie-Spur einer Runde aus
und gibt Kennzahlen + konkrete Verbesserungsvorschlaege.

Bewusst transparent und heuristisch (keine Black-Box): die Tipps stuetzen
sich auf nachvollziehbare Groessen wie Roll-Anteil (Coasting), Gas/Bremse-
Ueberlappung, Grip-Verlust (Combined Slip > 1) und - wenn eine schnellere
Referenzrunde vorliegt - die Streckenabschnitte mit dem groessten Zeitverlust.

Eine "Spur" (trace) ist ein spaltenweises Dict, siehe traces.py.
"""
from __future__ import annotations

from bisect import bisect_right

from .util import fmt_time


def _interp(xs: list[float], ys: list[float], x: float) -> float | None:
    if not xs:
        return None
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect_right(xs, x)
    x0, x1 = xs[i - 1], xs[i]
    y0, y1 = ys[i - 1], ys[i]
    return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def _pct(count: int, total: int) -> float:
    return round(100 * count / total, 1) if total else 0.0


def analyze_lap(trace: dict, reference: dict | None = None) -> dict:
    """Kennzahlen + Tipps fuer eine Runde. `reference` ist optional eine
    schnellere Vergleichsrunde (gleiches Auto/Strecke)."""
    ch = trace.get("channels", {})
    thr = ch.get("throttle", [])
    brk = ch.get("brake", [])
    spd = ch.get("speed_kmh", [])
    n = len(thr)
    slips = [ch.get(f"slip_{w}", []) for w in ("fl", "fr", "rl", "rr")]

    coasting = full_thr = braking = overlap = high_slip = 0
    for i in range(n):
        t = thr[i] if i < len(thr) else 0
        b = brk[i] if i < len(brk) else 0
        if t < 5 and b < 5:
            coasting += 1
        if t >= 95:
            full_thr += 1
        if b >= 5:
            braking += 1
        if t > 10 and b > 10:
            overlap += 1
        if any(i < len(s) and s[i] > 1.0 for s in slips):
            high_slip += 1

    stats = {
        "coasting_pct": _pct(coasting, n),
        "full_throttle_pct": _pct(full_thr, n),
        "braking_pct": _pct(braking, n),
        "overlap_pct": _pct(overlap, n),
        "high_slip_pct": _pct(high_slip, n),
        "max_speed_kmh": round(max(spd), 1) if spd else None,
        "min_speed_kmh": round(min(spd), 1) if spd else None,
        "samples": n,
    }

    delta_zones: list[dict] = []
    ref_info = None
    if reference and reference.get("channels", {}).get("dist"):
        delta_zones = _delta_zones(trace, reference)
        ref_info = {
            "lap_id": reference.get("lap_id"),
            "time": reference.get("time"),
            "time_seconds": reference.get("time_seconds"),
        }

    suggestions = _suggestions(stats, delta_zones, reference)
    return {
        "stats": stats,
        "suggestions": suggestions,
        "delta_zones": delta_zones,
        "reference": ref_info,
    }


def _delta_zones(trace: dict, reference: dict, segment_m: float = 100.0) -> list[dict]:
    """Zeitverlust ggue. Referenz pro Streckensegment (~100 m), groesste zuerst."""
    d = trace["channels"]["dist"]
    t = trace["channels"]["t"]
    rd = reference["channels"]["dist"]
    rt = reference["channels"]["t"]
    if not d or not rd:
        return []
    total = d[-1]
    zones = []
    start = 0.0
    while start < total:
        end = min(start + segment_m, total)
        # Zeit fuer das Segment in beiden Runden (interpoliert)
        cur = _interp(d, t, end) - _interp(d, t, start)
        ref = _interp(rd, rt, end) - _interp(rd, rt, start)
        lost = cur - ref
        if lost > 0.03:  # nur echte Verluste
            zones.append({"from_m": round(start), "to_m": round(end),
                          "lost_s": round(lost, 2)})
        start = end
    zones.sort(key=lambda z: z["lost_s"], reverse=True)
    return zones[:3]


def _suggestions(stats: dict, zones: list[dict], reference: dict | None) -> list[dict]:
    """Strukturierte Tipps: je {code, params, text}. `code`+`params` erlauben
    der UI eine eigene Lokalisierung (DE/EN); `text` ist der deutsche Fallback."""
    out = []

    def add(code, params, text):
        out.append({"code": code, "params": params, "text": text})

    if zones:
        z = zones[0]
        add("delta_zone", z,
            f"Groesster Zeitverlust ggue. deiner Bestrunde: {z['from_m']}-{z['to_m']} m "
            f"(+{z['lost_s']:.2f} s). Dort Bremspunkt, Linie und Kurvenausgang pruefen.")
    if stats["coasting_pct"] >= 12:
        add("coasting", {"pct": stats["coasting_pct"]},
            f"Du rollst {stats['coasting_pct']:.0f}% der Runde ohne Gas/Bremse - "
            f"spaeter bremsen oder frueher wieder ans Gas spart Zeit.")
    if stats["overlap_pct"] >= 4:
        add("overlap", {"pct": stats["overlap_pct"]},
            f"Gas und Bremse ueberlappen {stats['overlap_pct']:.0f}% - sauberere "
            f"Trennung (erst loesen, dann Gas) bringt Stabilitaet.")
    if stats["high_slip_pct"] >= 15:
        add("high_slip", {"pct": stats["high_slip_pct"]},
            f"Haeufiger Grip-Verlust ({stats['high_slip_pct']:.0f}% Slip>1) - sanftere "
            f"Lenk- und Gasimpulse, besonders am Kurvenausgang.")
    if 0 < stats["full_throttle_pct"] < 35:
        add("low_full_throttle", {"pct": stats["full_throttle_pct"]},
            f"Nur {stats['full_throttle_pct']:.0f}% Vollgas - auf den Geraden frueher "
            f"voll aufs Gas, wenn das Heck stabil bleibt.")
    if not out:
        add("clean", {}, "Saubere Runde - keine groben Schwaechen erkennbar. "
                         "Feinschliff an Bremspunkten und Kurvenausgaengen.")
    if reference is None:
        add("need_reference", {}, "Tipp: Fahr eine weitere Runde mit demselben Auto - "
                                  "dann vergleiche ich die Abschnitte mit deiner Bestrunde.")
    return out
