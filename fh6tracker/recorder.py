"""Trace-Recorder: schneidet eine Time-Attack-Session als CSV mit.

Schreibt pro empfangenem Paket eine Zeile (t_rel, x, z, race_on, ...).
Damit kalibrieren wir die Linien-Erkennung gegen echte Fahrdaten.

Starten (im Projektordner):
    py -m fh6tracker.recorder
    py -m fh6tracker.recorder --out meine_runde.csv

Voraussetzung: In FH6  Einstellungen > HUD > Data Out = AN,
IP 127.0.0.1, Port 5300.
"""
from __future__ import annotations

import argparse
import csv
import socket
import sys
import time
from datetime import datetime

from . import telemetry as tel

FIELDS = [
    "t_rel", "x", "z", "race_on", "ordinal", "car_class", "pi", "drivetrain",
]


def record(out_path: str, host: str = "0.0.0.0", port: int = 5300) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError as e:
        print(f"FEHLER: Port {port} nicht oeffenbar ({e}).")
        sys.exit(1)
    sock.settimeout(2.0)

    print("=" * 62)
    print("  FH6 Trace-Recorder laeuft")
    print(f"  UDP-Port {port}  |  schreibt -> {out_path}")
    print("  Fahr eine komplette Time-Attack-Runde (am besten 2-3),")
    print("  dann mit Strg+C beenden und die CSV hochladen.")
    print("=" * 62)

    n = 0
    n_world = 0
    t0 = None
    last_print = 0.0
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(FIELDS)
        try:
            while True:
                try:
                    data, _ = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                pkt = tel.parse(data)
                if pkt is None:
                    continue
                now = time.perf_counter()
                if t0 is None:
                    t0 = now
                t_rel = now - t0
                writer.writerow([
                    f"{t_rel:.4f}", f"{pkt.x:.3f}", f"{pkt.z:.3f}",
                    pkt.race_on, pkt.ordinal, pkt.car_class, pkt.pi,
                    pkt.drivetrain,
                ])
                n += 1
                if pkt.in_world:
                    n_world += 1
                if now - last_print > 1.0:
                    last_print = now
                    fh.flush()
                    print(f"  Pakete: {n:6d}  (in Welt: {n_world:6d})  "
                          f"x={pkt.x:8.1f} z={pkt.z:8.1f} raceOn={pkt.race_on}",
                          end="\r", flush=True)
        except KeyboardInterrupt:
            print(f"\n  Fertig. {n} Pakete in {out_path} geschrieben.")
        finally:
            sock.close()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="FH6 Telemetrie-Trace aufzeichnen")
    ap.add_argument("--out", default=None,
                    help="Ziel-CSV (Standard: ta_trace_<Zeitstempel>.csv)")
    ap.add_argument("--port", type=int, default=5300)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args(argv)
    out = args.out or datetime.now().strftime("ta_trace_%Y%m%d_%H%M%S.csv")
    record(out, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
