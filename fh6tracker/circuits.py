"""Strecken-Datenbank: bekannte Start/Ziel-Linien (Position + Heading).

Format circuits.csv (neu):
    circuit, center_x, center_z, heading_x, heading_z, half_width

Eine Strecke ist eine gerichtete Start/Ziel-Linie. Aus ihr wird per
`gate()` ein LineGate gebaut. Bekannte Strecken werden beim Fahren sofort
wiedererkannt (kein Lern-Runde noetig) - das ist die Basis fuer Baustein 2.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass

from . import geometry as g
from .gate import LineGate

# 10 m Halbbreite (= 20 m Linie). Aus echten Traces: Ideallinien variieren
# seitlich um mehrere Meter; 2.5 m verfehlt Durchfahrten, 10 m faengt sie
# zuverlaessig ohne Fehlausloeser (Richtungspruefung schuetzt zusaetzlich).
DEFAULT_HALF_WIDTH = 10.0
HEADER = ["circuit", "center_x", "center_z", "heading_x", "heading_z", "half_width"]


@dataclass
class Circuit:
    name: str
    center: g.Vec
    heading: g.Vec
    half_width: float = DEFAULT_HALF_WIDTH

    def gate(self) -> LineGate:
        return LineGate(self.center, self.heading, self.half_width)


class CircuitStore:
    """Laedt/speichert bekannte Strecken aus circuits.csv."""

    def __init__(self, path: str):
        self.path = path
        self.items: list[Circuit] = []
        if os.path.exists(path):
            self._load()
        else:
            self._write_header()

    def _load(self) -> None:
        with open(self.path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    self.items.append(Circuit(
                        name=row["circuit"],
                        center=(float(row["center_x"]), float(row["center_z"])),
                        heading=(float(row["heading_x"]), float(row["heading_z"])),
                        half_width=float(row.get("half_width") or DEFAULT_HALF_WIDTH),
                    ))
                except (KeyError, ValueError, TypeError):
                    # Zeile unvollstaendig/legacy -> ueberspringen
                    continue

    def _write_header(self) -> None:
        with open(self.path, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow(HEADER)

    def add(self, circuit: Circuit) -> None:
        self.items.append(circuit)
        write_header = not os.path.exists(self.path) or os.path.getsize(self.path) == 0
        with open(self.path, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if write_header:
                w.writerow(HEADER)
            w.writerow([
                circuit.name,
                round(circuit.center[0], 2), round(circuit.center[1], 2),
                round(circuit.heading[0], 5), round(circuit.heading[1], 5),
                circuit.half_width,
            ])

    def nearest(self, x: float, z: float, max_dist: float) -> Circuit | None:
        """Naechste bekannte Strecke, deren Linien-Mittelpunkt < max_dist liegt."""
        best: Circuit | None = None
        best_d = max_dist
        for c in self.items:
            d = g.dist((x, z), c.center)
            if d < best_d:
                best, best_d = c, d
        return best

    def next_auto_name(self) -> str:
        return f"Strecke {len(self.items) + 1}"
