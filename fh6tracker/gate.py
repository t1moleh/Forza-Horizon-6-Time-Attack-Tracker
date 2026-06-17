"""Start/Ziel als Liniensegment mit echter Ueberquerungs-Erkennung.

Statt eines Punkt-Radius (ungenau, ~6 s Versatz) wird die Start/Ziel-Linie
als kurzes Segment quer zur Fahrtrichtung modelliert:

    - center   : Mittelpunkt der Linie (x, z)
    - heading  : Einheits-Fahrtrichtung beim Ueberqueren (zeigt "nach vorn")
    - half_width: halbe Linienbreite (Default 2.5 m -> 5 m Gesamtbreite)

Die eigentliche Linie liegt SENKRECHT zum heading. Eine Ueberquerung wird
zwischen zwei aufeinanderfolgenden Positionspaketen erkannt: kreuzt der
Fahrweg p0->p1 die Linie in heading-Richtung (von hinten nach vorn), wird
der Bruchteil f des Schnitts berechnet und daraus der Zeitpunkt linear
interpoliert. Das beseitigt den paketbedingten Zeitversatz.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import geometry as g


@dataclass(frozen=True)
class Crossing:
    """Ergebnis einer erkannten Ueberquerung zwischen zwei Paketen."""

    fraction: float          # Anteil [0,1) entlang p0->p1, wo gekreuzt wurde
    time: float              # interpolierter Zeitpunkt der Ueberquerung
    point: g.Vec             # interpolierter Schnittpunkt (x, z)
    lateral: float           # seitlicher Versatz vom Mittelpunkt (m, vorzeichenbeh.)


class LineGate:
    """Eine gerichtete Start/Ziel-Linie."""

    def __init__(self, center: g.Vec, heading: g.Vec, half_width: float = 2.5):
        h = g.normalize(heading)
        if h == (0.0, 0.0):
            raise ValueError("heading darf nicht der Nullvektor sein")
        self.center: g.Vec = center
        self.heading: g.Vec = h
        self.perp: g.Vec = g.perpendicular(h)
        self.half_width: float = half_width

    # -- Geometrie -----------------------------------------------------------

    def signed_along(self, p: g.Vec) -> float:
        """Signierter Abstand entlang heading (negativ = hinter der Linie)."""
        return g.dot(g.sub(p, self.center), self.heading)

    def endpoints(self) -> tuple[g.Vec, g.Vec]:
        """Die beiden Linienenden - fuers Zeichnen/Debuggen."""
        off = g.scale(self.perp, self.half_width)
        return (g.add(self.center, off), g.sub(self.center, off))

    def cross(
        self, p0: g.Vec, t0: float, p1: g.Vec, t1: float
    ) -> Crossing | None:
        """Prueft den Fahrweg p0(t0) -> p1(t1) auf eine Vorwaerts-Ueberquerung.

        Gibt ein Crossing zurueck, wenn der Weg die Linie in heading-Richtung
        kreuzt und der Schnittpunkt innerhalb der Linienbreite liegt; sonst None.
        """
        d0 = self.signed_along(p0)
        d1 = self.signed_along(p1)
        # Nur Vorwaerts-Ueberquerung: von hinter der Linie (<=0) nach davor (>0).
        if not (d0 <= 0.0 < d1):
            return None
        denom = d1 - d0
        f = -d0 / denom  # in [0,1), da d0<=0<d1
        point = g.lerp(p0, p1, f)
        lateral = g.dot(g.sub(point, self.center), self.perp)
        if abs(lateral) > self.half_width:
            return None
        time = t0 + (t1 - t0) * f
        return Crossing(fraction=f, time=time, point=point, lateral=lateral)
