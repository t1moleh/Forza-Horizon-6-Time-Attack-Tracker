"""2D-Vektorhelfer fuer die Mess-Logik (Ebene x/z, Hoehe ignoriert).

Bewusst rein (keine Netzwerk-/IO-Abhaengigkeit), damit die Linien-
Ueberquerung exakt gegen synthetische Fahrten getestet werden kann.
"""
from __future__ import annotations

import math

Vec = tuple[float, float]


def sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1])


def add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1])


def scale(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k)


def dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1]


def cross(a: Vec, b: Vec) -> float:
    """2D-Kreuzprodukt (Skalar)."""
    return a[0] * b[1] - a[1] * b[0]


def length(a: Vec) -> float:
    return math.hypot(a[0], a[1])


def dist(a: Vec, b: Vec) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def normalize(a: Vec) -> Vec:
    m = math.hypot(a[0], a[1])
    return (a[0] / m, a[1] / m) if m else (0.0, 0.0)


def perpendicular(a: Vec) -> Vec:
    """90-Grad-Drehung gegen den Uhrzeigersinn."""
    return (-a[1], a[0])


def lerp(a: Vec, b: Vec, f: float) -> Vec:
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
