"""Optionaler Versionsabgleich mit der oeffentlichen GitHub-Releases-API.

Bewusst minimal und privacy-bewusst: EIN read-only GET an die oeffentliche
GitHub-API pro Start, um die neueste Release-Version zu lesen. Es werden KEINE
Spiel- oder Nutzerdaten gesendet (nur das, was jeder HTTPS-Request preisgibt).
Kein API-Key noetig. Offline/Timeout/Rate-Limit werden sauber abgefangen
(Ergebnis dann einfach None - nie ein Absturz, nie blockierend).
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from urllib.error import HTTPError, URLError

_REPO = "t1moleh/Forza-Horizon-6-Time-Attack-Tracker"
_API = f"https://api.github.com/repos/{_REPO}/releases/latest"
_RELEASES_PAGE = f"https://github.com/{_REPO}/releases/latest"


def _ver(v: str) -> tuple:
    """'v0.2.0' / '0.2.0' -> (0, 2, 0) fuer den Vergleich. Leer bei Unsinn."""
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums) if nums else ()


def fetch_latest(current: str, timeout: float = 4.0) -> dict | None:
    """{'latest': <str>, 'url': <str>} wenn eine NEUERE Version vorliegt, sonst
    None. Jeder Fehler (offline, Rate-Limit, Timeout, Murks) -> None."""
    try:
        req = urllib.request.Request(_API, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "FH6LapTracker",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (HTTPError, URLError, ValueError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    tag = str(data.get("tag_name") or "")
    latest, cur = _ver(tag), _ver(current)
    if latest and cur and latest > cur:
        return {"latest": tag.lstrip("vV") or tag,
                "url": data.get("html_url") or _RELEASES_PAGE}
    return None


# Kurzer Prozess-Cache, damit Reloads des Dashboards nicht wiederholt die
# GitHub-API treffen. Auch ein "kein Update / offline"-Ergebnis wird gecacht.
_cache: dict = {"t": 0.0, "val": None}
_TTL = 900.0  # 15 Minuten


def cached_latest(current: str, ttl: float = _TTL) -> dict | None:
    """Wie fetch_latest, aber mit kurzem Cache. Wird vom /api/update-Endpunkt
    genutzt - die Pruefung passiert nur, wenn das Dashboard sie anfordert (und
    das tut es nur, wenn die automatische Suche eingeschaltet ist)."""
    now = time.time()
    if _cache["t"] and (now - _cache["t"]) < ttl:
        return _cache["val"]
    _cache["val"] = fetch_latest(current)
    _cache["t"] = now
    return _cache["val"]
