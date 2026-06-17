"""Tracker-Runner: verbindet Engine + Strecken-DB + Persistenz.

Zwei Modi:
  Live  : empfaengt UDP-Pakete von FH6 Data Out und misst Runden.
  Replay: spielt eine aufgezeichnete ta_trace.csv durch dieselbe Engine -
          zum Kalibrieren/Verifizieren gegen echte Daten (kein Spiel noetig).

    py -m fh6tracker.tracker                 # live
    py -m fh6tracker.tracker --replay ta_trace.csv
    py -m fh6tracker.tracker --replay ta_trace.csv --save-circuit
"""
from __future__ import annotations

import argparse
import csv
import os
import socket
import sys
import time
from datetime import datetime

from . import geometry as g
from . import telemetry as tel
from .analysis import analyze_lap
from .circuits import Circuit, CircuitStore
from .engine import LapEngine, LapEvent
from .ghost import GhostComparer
from . import traces as tr
from .session import SessionState
from .snapshot import build_state
from .storage import NameStore, delete_lap, ensure_log, log_lap, rebuild_bestlaps
from .util import fmt_time
from .webserver import start_web_server

# Projekt-Wurzel = Ordner ueber dem Paket (dort liegen die CSV-Dateien).
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _frozen() -> bool:
    return getattr(sys, "frozen", False)


def bundle_dir() -> str:
    """Ordner der MITGELIEFERTEN Ressourcen (web/, Default-CSVs).
    Als .exe (PyInstaller) liegen sie im temporaeren _MEIPASS, sonst im Projekt."""
    return getattr(sys, "_MEIPASS", PROJECT_ROOT) if _frozen() else PROJECT_ROOT


def user_data_dir() -> str:
    """Ordner fuer SCHREIBBARE Nutzerdaten (lap_times, bestlaps, laps/, circuits).
    Als .exe neben der .exe, sonst im Projekt."""
    return os.path.dirname(sys.executable) if _frozen() else PROJECT_ROOT


def seed_defaults(data_dir: str) -> None:
    """Default-Dateien (car_names.csv, circuits.csv) beim ersten Start neben die
    .exe kopieren, damit sie dort schreibbar vorliegen."""
    import shutil
    for name in ("car_names.csv", "circuits.csv"):
        dst = os.path.join(data_dir, name)
        src = os.path.join(bundle_dir(), name)
        if not os.path.exists(dst) and os.path.exists(src):
            try:
                shutil.copy(src, dst)
            except OSError:
                pass


def _paths(data_dir: str) -> dict[str, str]:
    return {
        "names": os.path.join(data_dir, "car_names.csv"),
        "circuits": os.path.join(data_dir, "circuits.csv"),
        "log": os.path.join(data_dir, "lap_times.csv"),
        "best": os.path.join(data_dir, "bestlaps.csv"),
        "traces": os.path.join(data_dir, "laps"),
    }


def load_lap_analysis(paths: dict[str, str], lap_id: str) -> dict | None:
    """Spur + (beste) Vergleichsrunde + Analyse fuer /api/lap/<id>."""
    trace = tr.load_trace(paths["traces"], lap_id)
    if trace is None:
        return None
    ref_id = tr.best_lap_id_for(paths["log"], trace.get("car_name", ""),
                                trace.get("track", ""), exclude_id=lap_id)
    reference = tr.load_trace(paths["traces"], ref_id) if ref_id else None
    return {
        "lap": {k: trace[k] for k in trace if k != "channels"},
        "channels": trace["channels"],
        "analysis": analyze_lap(trace, reference),
    }


def _print_best(rows) -> None:
    if not rows:
        return
    print("\n   Bestzeiten (Tool-Stoppuhr):")
    print("   " + "-" * 58)
    print(f"   {'Strecke':<14}{'Auto':<22}{'Kl.':<5}{'Zeit':>10}")
    print("   " + "-" * 58)
    for (auto, strecke), (tsec, r) in rows:
        print(f"   {strecke:<14}{auto[:21]:<22}{r['klasse']:<5}{fmt_time(tsec):>10}")
    print("   " + "-" * 58 + "\n")


def _make_engine(data_dir: str, save_new_circuits: bool):
    """Engine + Namensgeber, der neue Strecken optional in circuits.csv schreibt."""
    p = _paths(data_dir)
    names = NameStore(p["names"])
    store = CircuitStore(p["circuits"])
    ensure_log(p["log"])

    def namer(center: g.Vec, heading: g.Vec) -> str:
        name = store.next_auto_name()
        if save_new_circuits:
            store.add(Circuit(name=name, center=center, heading=heading))
        return name

    engine = LapEngine(circuits=list(store.items), namer=namer)
    return engine, names, store, p


def _handle_event(ev: LapEvent, names: NameStore, paths: dict[str, str],
                  quiet=False, is_best=False, lap_id: str = ""):
    auto = names.display(ev.car.ordinal)
    log_lap(paths["log"], ev, auto, lap_id)
    if ev.approximate:
        tag = "  (erste Runde, Schaetzung)"
    elif is_best:
        tag = "  *** NEUE BESTZEIT ***"
    else:
        tag = ""
    print(f"\n  >> Runde: {fmt_time(ev.lap_time):>9}  |  {auto} "
          f"({ev.car.class_name}, PI {ev.car.pi})  |  {ev.circuit}{tag}")
    if not quiet:
        _print_best(rebuild_bestlaps(paths["log"], paths["best"]))


# -- Live --------------------------------------------------------------------

def run_live(data_dir: str, host: str, port: int,
             web: bool = True, web_port: int = 8770,
             web_dir: str | None = None) -> None:
    engine, names, store, paths = _make_engine(data_dir, save_new_circuits=True)
    session = SessionState()
    ghost = GhostComparer()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError as e:
        print(f"FEHLER: Port {port} nicht oeffenbar ({e}).")
        sys.exit(1)
    sock.settimeout(2.0)

    def lap_fn(lap_id: str):
        return load_lap_analysis(paths, lap_id)

    def delete_fn(lap_id: str) -> bool:
        return delete_lap(paths["log"], lap_id, paths["traces"], paths["best"])

    web_url = None
    if web:
        try:
            kw = {"web_dir": web_dir} if web_dir else {}
            start_web_server(lambda: build_state(session, paths["log"], paths["traces"]),
                             port=web_port, lap_fn=lap_fn, delete_fn=delete_fn, **kw)
            web_url = f"http://127.0.0.1:{web_port}"
            try:
                import webbrowser
                webbrowser.open(web_url)
            except Exception:
                pass
        except OSError as e:
            print(f"  (Web-Dashboard konnte nicht starten: {e})")

    print("=" * 62)
    print("  FH6 Time-Attack-Tracker laeuft")
    print(f"  UDP-Port {port}  |  bekannte Strecken: {len(store.items)}")
    if web_url:
        print(f"  Dashboard: {web_url}")
    print("  Auf einen Circuit fahren - bekannte Strecken werden sofort")
    print("  erkannt, unbekannte nach der ersten vollen Runde gelernt.")
    print("  Beenden mit Strg+C.")
    print("=" * 62)

    last_status = 0.0
    # Telemetrie-Puffer der laufenden Runde (fuer die Per-Runde-Spur)
    buf = tr.empty_channels()
    buf_start: float | None = None
    last_sd = -1e9
    try:
        while True:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            pkt = tel.parse(data)
            if pkt is None:
                continue
            t = time.perf_counter()
            telem = tel.parse_telemetry(data)
            session.note_packet(pkt, names.display)
            session.note_telemetry(telem)
            ev = engine.update(t, pkt)
            # Live-Delta zur Ghost-Referenz (laufende Runde vs. Bestzeit)
            live_delta = None
            if (engine.circuit_name and engine.lap_start_t is not None
                    and pkt.race_on):
                live_delta = ghost.delta(pkt.ordinal, engine.circuit_name,
                                         engine.lap_dist, t - engine.lap_start_t)
            session.note_engine(engine.circuit_name, engine.lap_start_t, live_delta)

            if ev is not None:
                # Jede Runde bekommt eine eindeutige ID (fuer Loeschen/Referenz).
                lap_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3] + f"_{ev.car.ordinal}"
                # Spur nur bei praeziser Runde mit Aufzeichnung speichern
                if not ev.approximate and buf["dist"]:
                    tr.save_trace(paths["traces"], {
                        "lap_id": lap_id, "car_name": names.display(ev.car.ordinal),
                        "car_ordinal": ev.car.ordinal, "track": ev.circuit,
                        "time_seconds": round(ev.lap_time, 3),
                        "time": fmt_time(ev.lap_time), "channels": buf,
                    })
                is_best = session.add_lap(ev, names.display(ev.car.ordinal))
                if not ev.approximate:
                    ghost.consider(ev.car.ordinal, ev.circuit, ev.lap_time, ev.profile)
                _handle_event(ev, names, paths, is_best=is_best, lap_id=lap_id)

            # Spur der (neuen) laufenden Runde puffern
            if not pkt.race_on or engine.lap_start_t is None:
                buf, buf_start, last_sd = tr.empty_channels(), None, -1e9
            else:
                if engine.lap_start_t != buf_start:
                    buf, buf_start, last_sd = tr.empty_channels(), engine.lap_start_t, -1e9
                if telem and (engine.lap_dist - last_sd) >= engine.cfg.sample_dist:
                    last_sd = engine.lap_dist
                    tr.append_sample(buf, tr.sample_from(
                        engine.lap_dist, t - engine.lap_start_t, telem))

            if ev is None and pkt.race_on and (t - last_status) > 3.0:
                last_status = t
                where = engine.circuit_name or "suche Start/Ziel"
                state = "Runde laeuft" if engine.lap_start_t is not None else "bereit"
                print(f"  ... {where}  [{state}]  (gefahren: {engine.path_dist:.0f} m)")
    except KeyboardInterrupt:
        print("\nBeendet. Zeiten in lap_times.csv und bestlaps.csv.")
    finally:
        sock.close()


# -- Replay ------------------------------------------------------------------

def run_replay(trace_path: str, data_dir: str, save_circuit: bool) -> None:
    if not os.path.exists(trace_path):
        print(f"FEHLER: Trace nicht gefunden: {trace_path}")
        sys.exit(1)
    engine, names, store, paths = _make_engine(data_dir, save_new_circuits=save_circuit)

    print("=" * 62)
    print(f"  Replay: {trace_path}")
    print(f"  bekannte Strecken vorab: {len(store.items)}")
    print("=" * 62)

    n = 0
    events: list[LapEvent] = []
    with open(trace_path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                t = float(r["t_rel"])
                pkt = tel.Packet(
                    race_on=int(r["race_on"]),
                    ordinal=int(r["ordinal"]),
                    car_class=int(r["car_class"]),
                    pi=int(r["pi"]),
                    drivetrain=int(r["drivetrain"]),
                    x=float(r["x"]),
                    z=float(r["z"]),
                )
            except (KeyError, ValueError):
                continue
            n += 1
            ev = engine.update(t, pkt)
            if ev is not None:
                events.append(ev)
                _handle_event(ev, names, paths, quiet=True)

    print(f"\n  {n} Pakete verarbeitet, {len(events)} Runde(n) erkannt.")
    if engine.gate is not None:
        c = engine.gate.center
        h = engine.gate.heading
        print("\n  Ermittelte Start/Ziel-Linie:")
        print(f"    Mittelpunkt : x={c[0]:.2f}  z={c[1]:.2f}")
        print(f"    Heading     : ({h[0]:.5f}, {h[1]:.5f})")
        print(f"    -> circuits.csv: {engine.circuit_name},{c[0]:.2f},{c[1]:.2f},"
              f"{h[0]:.5f},{h[1]:.5f},2.5")
        if save_circuit:
            print("    (in circuits.csv gespeichert)")
    _print_best(rebuild_bestlaps(paths["log"], paths["best"]))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="FH6 Time-Attack-Tracker")
    ap.add_argument("--replay", metavar="TRACE", help="ta_trace.csv durchspielen statt live")
    ap.add_argument("--save-circuit", action="store_true",
                    help="beim Replay neu erkannte Strecke in circuits.csv schreiben")
    ap.add_argument("--data-dir", default=None, help="Ordner der CSV-Dateien")
    ap.add_argument("--port", type=int, default=5300)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--no-web", action="store_true", help="Web-Dashboard nicht starten")
    ap.add_argument("--web-port", type=int, default=8770)
    args = ap.parse_args(argv)

    data_dir = args.data_dir or user_data_dir()
    seed_defaults(data_dir)                         # Default-CSVs neben die .exe
    web_dir = os.path.join(bundle_dir(), "web")     # mitgelieferte UI

    if args.replay:
        run_replay(args.replay, data_dir, args.save_circuit)
    else:
        run_live(data_dir, args.host, args.port,
                 web=not args.no_web, web_port=args.web_port, web_dir=web_dir)


if __name__ == "__main__":
    main()
