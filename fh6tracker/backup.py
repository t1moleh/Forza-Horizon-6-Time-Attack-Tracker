"""Export/Import aller Nutzerdaten als ZIP - manuelles Backup ueber Updates
hinweg (zusaetzlich zur automatischen %APPDATA%-Ablage).

Export: packt die Daten-CSVs + den laps/-Telemetrieordner in ein ZIP.
Import: spielt ein solches ZIP zurueck. Sicher gegen Pfad-Traversal (Zip-Slip):
es werden nur fest definierte Dateinamen bzw. laps/<name>.json uebernommen.
"""
from __future__ import annotations

import io
import os
import zipfile

_FILES = ("lap_times.csv", "bestlaps.csv", "circuits.csv",
          "car_names.csv", "car_meta.csv")
_LAPS = "laps"


def export_zip(data_dir: str) -> bytes:
    """Alle vorhandenen Nutzerdaten als ZIP-Bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in _FILES:
            p = os.path.join(data_dir, name)
            if os.path.isfile(p):
                z.write(p, name)
        laps = os.path.join(data_dir, _LAPS)
        if os.path.isdir(laps):
            for fn in os.listdir(laps):
                fp = os.path.join(laps, fn)
                if os.path.isfile(fp) and fn.endswith(".json"):
                    z.write(fp, f"{_LAPS}/{fn}")
    return buf.getvalue()


def import_zip(data_dir: str, data: bytes) -> bool:
    """ZIP zurueckspielen. Nur Whitelist-Dateien + laps/*.json (Basename) -
    kein Pfad-Traversal. True bei Erfolg, False bei kaputtem/leerem ZIP."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            entries = z.namelist()
            if not entries:
                return False
            os.makedirs(data_dir, exist_ok=True)
            laps_dir = os.path.join(data_dir, _LAPS)
            wrote = False
            for entry in entries:
                norm = entry.replace("\\", "/")
                base = os.path.basename(norm)
                if norm in _FILES:
                    dst = os.path.join(data_dir, norm)
                elif norm.startswith(_LAPS + "/") and base.endswith(".json") and base:
                    os.makedirs(laps_dir, exist_ok=True)
                    dst = os.path.join(laps_dir, base)
                else:
                    continue  # alles andere ignorieren (Sicherheit)
                with z.open(entry) as src, open(dst, "wb") as out:
                    out.write(src.read())
                wrote = True
            return wrote
    except (zipfile.BadZipFile, OSError, ValueError):
        return False
