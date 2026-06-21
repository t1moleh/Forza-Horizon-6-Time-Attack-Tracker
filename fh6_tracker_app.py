"""Einstiegspunkt fuer die eigenstaendige .exe (PyInstaller, --noconsole).

Startet den FH6 Lap Tracker + lokales Dashboard. Als .exe liegen die
mitgelieferten Dateien (web/, car_names.csv, circuits.csv, car_meta.csv)
gebuendelt vor; Nutzerdaten + Logdatei liegen in %APPDATA%\\FH6LapTracker.

Da die .exe ohne Konsole laeuft (--noconsole), werden alle Ausgaben in eine
Logdatei im Nutzer-Datenordner umgeleitet (setup_file_logging) - sonst gaeben
print()-Aufrufe ins Leere bzw. wuerden Fehler werfen.
"""
import sys

from fh6tracker.tracker import main, setup_file_logging, user_data_dir

if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        setup_file_logging(user_data_dir())
    main()
