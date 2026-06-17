"""Kleine gemeinsame Helfer."""
from __future__ import annotations


def fmt_time(seconds: float | None) -> str:
    """Sekunden als m:ss.mmm (oder ss.mmm unter 1 Minute)."""
    if seconds is None or seconds <= 0:
        return "-"
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}:{s:06.3f}" if m else f"{s:.3f}"


def fmt_delta(seconds: float | None) -> str | None:
    """Vorzeichenbehaftete Differenz, z. B. '-0.437' (schneller) / '+1.726'."""
    if seconds is None:
        return None
    return f"{seconds:+.3f}"
