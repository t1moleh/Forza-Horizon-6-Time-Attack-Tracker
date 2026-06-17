"""Einstiegspunkt fuer die eigenstaendige .exe (PyInstaller).

Startet den FH6 Time-Attack-Tracker + lokales Dashboard. Als .exe liegen die
mitgelieferten Dateien (web/, car_names.csv, circuits.csv) gebuendelt vor;
Nutzerdaten (lap_times.csv, bestlaps.csv, laps/) entstehen neben der .exe.
"""
from fh6tracker.tracker import main

if __name__ == "__main__":
    main()
