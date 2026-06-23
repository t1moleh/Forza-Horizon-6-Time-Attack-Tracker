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
import logging
import logging.handlers
import os
import socket
import sys
import threading
import time
from datetime import datetime

from . import __version__
from . import geometry as g
from . import telemetry as tel
from .analysis import analyze_lap
from .circuits import Circuit, CircuitStore
from .engine import LapEngine, LapEvent
from .ghost import GhostComparer
from . import backup
from . import races as rc
from . import traces as tr
from . import update_check
from .rivals import RivalsTracker, is_rivals
from .session import SessionState
from .snapshot import build_state
from .storage import (NameStore, delete_lap, ensure_log, is_personal_best,
                      log_lap, rebuild_bestlaps)
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
    """Fester, update-sicherer Ordner fuer SCHREIBBARE Nutzerdaten
    (lap_times, bestlaps, laps/, circuits, car_names, car_meta).

    Frozen (.exe): %APPDATA%\\FH6LapTracker - bleibt erhalten, egal wohin die
    .exe verschoben oder ob sie ersetzt/aktualisiert wird (ueberlebt Updates).
    Bewusst NICHT _MEIPASS (Temp-Ordner, wird beim Beenden geloescht).
    Dev (Quelle): Projektordner."""
    if not _frozen():
        return PROJECT_ROOT
    base = os.environ.get("APPDATA") or os.path.dirname(sys.executable)
    d = os.path.join(base, "FH6LapTracker")
    os.makedirs(d, exist_ok=True)
    return d


# Schreibbare Nutzerdaten, die ein Update ueberleben muessen.
_USER_FILES = ("lap_times.csv", "bestlaps.csv", "circuits.csv",
               "car_names.csv", "car_meta.csv")


def migrate_legacy_data(data_dir: str) -> None:
    """Einmalige Migration: fruehere Versionen legten die CSVs NEBEN die .exe.
    Liegen dort Daten und im neuen %APPDATA%-Ordner noch keine lap_times.csv,
    werden Zeiten/Strecken/Traces uebernommen - so gehen beim Umstieg auf die
    update-sichere Ablage keine bestehenden Rundenzeiten verloren."""
    if not _frozen():
        return
    legacy = os.path.dirname(sys.executable)
    if os.path.abspath(legacy) == os.path.abspath(data_dir):
        return
    if os.path.exists(os.path.join(data_dir, "lap_times.csv")):
        return  # schon migriert / bereits Daten vorhanden
    if not os.path.exists(os.path.join(legacy, "lap_times.csv")):
        return  # nichts Altes zu uebernehmen
    import shutil
    for name in _USER_FILES:
        src, dst = os.path.join(legacy, name), os.path.join(data_dir, name)
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                shutil.copy2(src, dst)
            except OSError:
                pass
    src_laps, dst_laps = os.path.join(legacy, "laps"), os.path.join(data_dir, "laps")
    if os.path.isdir(src_laps) and not os.path.isdir(dst_laps):
        try:
            shutil.copytree(src_laps, dst_laps)
        except OSError:
            pass
    print(f"  (Bestehende Daten aus '{legacy}' nach '{data_dir}' uebernommen.)")


def seed_defaults(data_dir: str) -> None:
    """Default-Dateien (car_names.csv, circuits.csv, car_meta.csv) beim ersten
    Start in den Nutzer-Datenordner kopieren, damit sie schreibbar vorliegen."""
    import shutil
    for name in ("car_names.csv", "circuits.csv", "car_meta.csv"):
        dst = os.path.join(data_dir, name)
        src = os.path.join(bundle_dir(), name)
        if not os.path.exists(dst) and os.path.exists(src):
            try:
                shutil.copy(src, dst)
            except OSError:
                pass


class _StreamToLog:
    """Datei-artiges Objekt, das geschriebene Zeilen ins Logging schickt.
    Ersetzt sys.stdout/stderr, wenn es (als --noconsole-.exe) keine Konsole gibt
    - so landen bestehende print()-Ausgaben in der Logdatei statt zu crashen."""

    def __init__(self, level: int):
        self._level = level
        self._buf = ""

    def write(self, s):
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                logging.log(self._level, line.rstrip())

    def flush(self):
        if self._buf.strip():
            logging.log(self._level, self._buf.rstrip())
        self._buf = ""


def setup_file_logging(data_dir: str) -> str:
    """Ausgaben in eine rotierende Logdatei im Nutzer-Datenordner schreiben.

    Noetig fuer die --noconsole-.exe: ohne Konsole gibt es kein stdout, die
    vielen print()-Aufrufe gingen ins Leere bzw. wuerden Fehler werfen. Stattdessen
    wird hier alles geloggt (auch unbehandelte Ausnahmen) - gut fuer Bug-Reports."""
    log_path = os.path.join(data_dir, "fh6laptracker.log")
    try:
        os.makedirs(data_dir, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=512 * 1024, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s"))
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)
    except OSError:
        pass  # Logdatei nicht moeglich - trotzdem stdout/stderr umleiten (kein Crash)
    sys.stdout = _StreamToLog(logging.INFO)
    sys.stderr = _StreamToLog(logging.ERROR)
    sys.excepthook = lambda et, e, tb: logging.error(
        "Unbehandelte Ausnahme", exc_info=(et, e, tb))
    logging.info("=== FH6 Lap Tracker %s gestartet ===", __version__)
    return log_path


def _paths(data_dir: str) -> dict[str, str]:
    return {
        "names": os.path.join(data_dir, "car_names.csv"),
        "circuits": os.path.join(data_dir, "circuits.csv"),
        "car_meta": os.path.join(data_dir, "car_meta.csv"),
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


def _webview_available() -> bool:
    try:
        import webview  # noqa: F401
        return True
    except Exception:
        return False


def _open_browser(url: str) -> None:
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass


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
             web_dir: str | None = None, window: bool = True) -> None:
    engine, names, store, paths = _make_engine(data_dir, save_new_circuits=True)
    session = SessionState()
    ghost = GhostComparer()
    rivals = RivalsTracker()                                   # Rivals: Spiel-Timer
    race_list = rc.load_races(os.path.join(bundle_dir(), "races.csv"))  # Strecken-Namen

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
            start_web_server(lambda: build_state(session, paths["log"], paths["traces"], paths["car_meta"]),
                             port=web_port, lap_fn=lap_fn, delete_fn=delete_fn,
                             cars_dir=os.path.join(data_dir, "cars"),
                             update_fn=lambda: update_check.cached_latest(__version__),
                             export_fn=lambda: backup.save_export(data_dir),
                             import_fn=lambda b: backup.import_zip(data_dir, b), **kw)
            web_url = f"http://127.0.0.1:{web_port}"
        except OSError as e:
            print(f"  (Web-Dashboard konnte nicht starten: {e})")

    use_window = bool(window and web_url and _webview_available())

    print("=" * 62)
    print("  FH6 Time-Attack-Tracker laeuft")
    print(f"  UDP-Port {port}  |  bekannte Strecken: {len(store.items)}")
    if use_window:
        print("  UI: eigenes Programmfenster")
    elif web_url:
        print(f"  Dashboard im Browser: {web_url}")
    print("  Auf einen Circuit fahren - bekannte Strecken werden sofort erkannt.")
    print("  Beenden: Fenster schliessen." if use_window else "  Beenden mit Strg+C.")
    print("=" * 62)

    stop = threading.Event()

    def udp_loop():
        last_status = 0.0
        buf = tr.empty_channels()
        buf_start = None
        last_sd = -1e9
        while not stop.is_set():
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            pkt = tel.parse(data)
            if pkt is None:
                continue
            t = time.perf_counter()
            telem = tel.parse_telemetry(data)
            lt = tel.parse_lap_timing(data)          # spielinterne Lap-Timer
            session.note_packet(pkt, names.display)
            session.note_telemetry(telem)
            ev = engine.update(t, pkt)
            riv_ev = rivals.update(lt)               # fertige Rivals-Runde?
            rivals_mode = is_rivals(lt)
            session.note_mode("rivals" if rivals_mode else "timeattack")
            if rivals_mode:
                ev = None    # im Rivals-Modus NICHT die GPS-Runde loggen (Spiel-Timer gilt)
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
                car_name = names.display(ev.car.ordinal)
                # persoenliche Bestzeit (all-time) VOR dem Loggen pruefen
                record = (not ev.approximate and
                          is_personal_best(paths["log"], car_name, ev.circuit, ev.lap_time))
                is_best = session.add_lap(ev, car_name, is_record=record)
                if not ev.approximate:
                    ghost.consider(ev.car.ordinal, ev.circuit, ev.lap_time, ev.profile)
                _handle_event(ev, names, paths, is_best=is_best, lap_id=lap_id)

            if riv_ev is not None:
                # Rivals-Runde aus dem Spiel-Timer: Strecke ueber die Position
                # erkennen (labs.gg-Registry), Zeit kommt aus dem Spiel.
                near = rc.nearest_race(race_list, pkt.x, pkt.z)
                track_name = near.name if near else (engine.circuit_name or "Rivals")
                car_name = names.display(pkt.ordinal)
                lap_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3] + f"_{pkt.ordinal}"
                riv_lap = LapEvent(riv_ev.lap_time, t, track_name, pkt, approximate=False)
                log_lap(paths["log"], riv_lap, car_name, lap_id, modus="rivals")
                rebuild_bestlaps(paths["log"], paths["best"])
                print(f"\n  >> Rivals-Runde: {fmt_time(riv_ev.lap_time):>9}  |  "
                      f"{car_name}  |  {track_name}")

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
    if use_window:
        threading.Thread(target=udp_loop, daemon=True).start()
        try:
            import webview
            webview.create_window(f"FH6 Lap Tracker v{__version__}", web_url,
                                  width=1280, height=820, min_size=(900, 600))
            # private_mode=False + fester storage_path: localStorage (Sprache,
            # Theme, Accent, Sound, eigene Bilder) bleibt ueber Neustarts erhalten.
            webview.start(private_mode=False,
                          storage_path=os.path.join(data_dir, "webview"))
        except Exception as e:
            print(f"  (Eigenes Fenster nicht moeglich: {e}; oeffne Browser)")
            _open_browser(web_url)
            try:
                while not stop.is_set():
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass
    else:
        if web_url:
            _open_browser(web_url)
        try:
            udp_loop()
        except KeyboardInterrupt:
            pass

    stop.set()
    try:
        sock.close()
    except OSError:
        pass
    print("\nBeendet. Zeiten in lap_times.csv und bestlaps.csv.")


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
    ap.add_argument("--no-window", action="store_true",
                    help="kein eigenes Fenster - Dashboard im Browser oeffnen")
    ap.add_argument("--web-port", type=int, default=8770)
    args = ap.parse_args(argv)

    data_dir = args.data_dir or user_data_dir()
    if args.data_dir is None:
        migrate_legacy_data(data_dir)               # Daten alter Versionen uebernehmen
    seed_defaults(data_dir)                          # fehlende Default-CSVs ergaenzen
    web_dir = os.path.join(bundle_dir(), "web")      # mitgelieferte UI

    if args.replay:
        run_replay(args.replay, data_dir, args.save_circuit)
    else:
        run_live(data_dir, args.host, args.port,
                 web=not args.no_web, web_port=args.web_port, web_dir=web_dir,
                 window=not args.no_window)


if __name__ == "__main__":
    main()
