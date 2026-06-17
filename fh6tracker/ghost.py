"""Ghost-Vergleich: Live-Delta der laufenden Runde gegen die beste Runde.

Speichert je (Fahrzeug, Strecke) das Distanz-Zeit-Profil der bisher besten
Runde dieser Session. Waehrend der laufenden Runde wird zur aktuell
gefahrenen Distanz die Referenzzeit interpoliert und die Differenz gebildet:
positiv = langsamer als die Bestzeit, negativ = schneller.
"""
from __future__ import annotations

from bisect import bisect_right


class GhostComparer:
    def __init__(self):
        # (car_ordinal, track) -> (best_lap_seconds, dists[], times[])
        self._refs: dict[tuple[int, str], tuple[float, list[float], list[float]]] = {}

    def consider(self, car_ordinal: int, track: str, lap_seconds: float,
                 profile: tuple) -> bool:
        """Profil als neue Referenz uebernehmen, wenn es die schnellste Runde
        dieser (Auto, Strecke)-Kombi in der Session ist. Gibt True zurueck,
        wenn ein neuer Session-Rekord vorliegt."""
        key = (car_ordinal, track)
        prev = self._refs.get(key)
        if prev is not None and lap_seconds >= prev[0]:
            return False
        if profile:
            dists = [p[0] for p in profile]
            times = [p[1] for p in profile]
        else:
            dists, times = [], []
        self._refs[key] = (lap_seconds, dists, times)
        return True

    def has_reference(self, car_ordinal: int, track: str) -> bool:
        ref = self._refs.get((car_ordinal, track))
        return bool(ref and ref[1])

    def delta(self, car_ordinal: int, track: str, lap_dist: float,
              elapsed: float) -> float | None:
        """Differenz (s) der laufenden Runde zur Referenz an gleicher Distanz."""
        ref = self._refs.get((car_ordinal, track))
        if not ref or not ref[1]:
            return None
        _, dists, times = ref
        ref_t = _interp(dists, times, lap_dist)
        if ref_t is None:
            return None
        return elapsed - ref_t


def _interp(dists: list[float], times: list[float], d: float) -> float | None:
    """Lineare Interpolation der Zeit bei Distanz d (geklemmt an den Raendern)."""
    if not dists:
        return None
    if d <= dists[0]:
        return times[0]
    if d >= dists[-1]:
        return times[-1]
    i = bisect_right(dists, d)
    d0, d1 = dists[i - 1], dists[i]
    t0, t1 = times[i - 1], times[i]
    if d1 == d0:
        return t0
    return t0 + (t1 - t0) * (d - d0) / (d1 - d0)
