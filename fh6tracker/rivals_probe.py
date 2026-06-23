"""Rivals-Probe (Diagnose): liest die spielinternen Lap-Timer-Felder aus dem
FH6-"Data Out"-Stream und zeigt live, ob Forza sie befuellt.

Hintergrund: Im Open-World-Time-Attack bleiben CurrentLapTime/LastLapTime/
BestLapTime/LapNumber leer (0) - deshalb misst das Tool Runden selbst per
GPS-Stoppuhr. Rivals ist ein strukturierter, getimter Modus; sehr wahrscheinlich
befuellt Forza dort diese Felder. Falls ja, koennte der Rivals-Modus den
spielinternen Timer direkt nutzen statt der positionsbasierten Messung.

Read-only, rein lokal (sendet nichts). WICHTIG: zuerst den Lap Tracker schliessen,
beide koennen denselben UDP-Port nicht gleichzeitig empfangen.

    py -m fh6tracker.rivals_probe
    py -m fh6tracker.rivals_probe --port 5300
"""
from __future__ import annotations

import argparse
import socket
import sys
import time

from . import telemetry as tel


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="FH6 Rivals-Probe: prueft, ob die Lap-Timer-Felder befuellt sind")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=5300)
    args = ap.parse_args(argv)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((args.host, args.port))
    except OSError as e:
        print(f"FEHLER: Port {args.port} nicht oeffenbar ({e}).")
        print("Tipp: Laeuft der Lap Tracker noch? Bitte zuerst schliessen - "
              "beide koennen den Port nicht gleichzeitig empfangen.")
        sys.exit(1)
    sock.settimeout(2.0)

    print("=" * 66)
    print("  FH6 Rivals-Probe - prueft die spielinternen Lap-Timer-Felder")
    print(f"  UDP-Port {args.port}  |  In FH6: Data Out = ON, 127.0.0.1:{args.port}")
    print("  Starte eine RIVALS-Session und fahre ein paar Runden.")
    print("  Beenden mit Strg+C -> danach kommt das Fazit.")
    print("=" * 66)

    any_nonzero = False
    got_packet = False
    max_lap = 0
    last_line = 0.0
    last_lastlap: float | None = None
    try:
        while True:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            lt = tel.parse_lap_timing(data)
            if lt is None:
                continue
            got_packet = True
            if lt["current_lap"] or lt["last_lap"] or lt["best_lap"] or lt["lap_number"]:
                any_nonzero = True
            max_lap = max(max_lap, lt["lap_number"])

            # Rundenwechsel (LastLap aendert sich) als Ereignis ausgeben
            if last_lastlap is not None and lt["last_lap"] != last_lastlap \
                    and lt["last_lap"] > 0:
                print(f"\n  >> Runde fertig: LastLap = {lt['last_lap']:.3f}s  "
                      f"(Lap #{lt['lap_number']}, Best {lt['best_lap']:.3f}s)")
            last_lastlap = lt["last_lap"]

            now = time.perf_counter()
            if now - last_line > 0.4:
                last_line = now
                sys.stdout.write(
                    f"\r  race_on={lt['race_on']}  Lap#{lt['lap_number']:<2}  "
                    f"cur={lt['current_lap']:8.3f}  last={lt['last_lap']:8.3f}  "
                    f"best={lt['best_lap']:8.3f}  raceT={lt['current_race_time']:7.1f}  "
                    f"dist={lt['distance']:8.1f}   ")
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass

    print("\n" + "=" * 66)
    if not got_packet:
        print("  Keine Pakete empfangen. Ist 'Data Out' an und der Port korrekt?")
    elif any_nonzero:
        print("  ERGEBNIS: Die Lap-Timer-Felder SIND befuellt.")
        print("  -> Rivals kann den spielinternen Timer direkt nutzen (einfacher Weg).")
        print(f"  (hoechste gesehene Lap-Nummer: {max_lap})")
    else:
        print("  ERGEBNIS: Die Lap-Timer-Felder blieben 0 (wie im Time Attack).")
        print("  -> Rivals braucht eigene Linien-/Checkpoint-Erkennung wie die")
        print("     Open-World-Circuits.")
    print("=" * 66)


if __name__ == "__main__":
    main()
