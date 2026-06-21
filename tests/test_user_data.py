"""Tests fuer den update-sicheren Datenordner (%APPDATA%) + Legacy-Migration."""
import csv
import logging
import os
import sys

import fh6tracker.tracker as T


def _frozen_env(monkeypatch, legacy_dir, appdata_dir):
    """Simuliert eine .exe: sys.frozen, sys.executable neben legacy_dir, APPDATA."""
    monkeypatch.setattr(T.sys, "frozen", True, raising=False)
    monkeypatch.setattr(T.sys, "executable",
                        os.path.join(legacy_dir, "FH6 Lap Tracker.exe"))
    monkeypatch.setenv("APPDATA", appdata_dir)


def test_user_data_dir_uses_appdata(tmp_path, monkeypatch):
    _frozen_env(monkeypatch, str(tmp_path / "app"), str(tmp_path / "appdata"))
    d = T.user_data_dir()
    assert d == os.path.join(str(tmp_path / "appdata"), "FH6LapTracker")
    assert os.path.isdir(d)                     # wird angelegt


def test_migrate_legacy_data_moves_times(tmp_path, monkeypatch):
    legacy = tmp_path / "app"
    legacy.mkdir()
    appdata = tmp_path / "appdata"
    _frozen_env(monkeypatch, str(legacy), str(appdata))

    # Legacy-Daten neben der .exe (wie v0.2.0)
    with open(legacy / "lap_times.csv", "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows([["datum_uhrzeit", "auto", "rundenzeit_s"],
                                  ["2026-06-19", "Ferrari 355", "95.1"]])
    (legacy / "circuits.csv").write_text("name\n", encoding="utf-8")
    (legacy / "laps").mkdir()
    (legacy / "laps" / "x1.json").write_text("{}", encoding="utf-8")

    d = T.user_data_dir()
    T.migrate_legacy_data(d)

    assert os.path.exists(os.path.join(d, "lap_times.csv"))
    assert os.path.exists(os.path.join(d, "circuits.csv"))
    assert os.path.isfile(os.path.join(d, "laps", "x1.json"))


def test_migrate_is_idempotent(tmp_path, monkeypatch):
    legacy = tmp_path / "app"
    legacy.mkdir()
    appdata = tmp_path / "appdata"
    _frozen_env(monkeypatch, str(legacy), str(appdata))
    (legacy / "lap_times.csv").write_text("orig", encoding="utf-8")

    d = T.user_data_dir()
    T.migrate_legacy_data(d)
    # Legacy aendern; zweite Migration darf NICHT erneut kopieren/ueberschreiben
    (legacy / "lap_times.csv").write_text("CHANGED", encoding="utf-8")
    T.migrate_legacy_data(d)
    assert open(os.path.join(d, "lap_times.csv")).read() == "orig"


def test_no_migration_when_not_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(T.sys, "frozen", False, raising=False)
    # Dev-Modus: user_data_dir == Projektordner, Migration ist No-op
    assert T.user_data_dir() == T.PROJECT_ROOT
    T.migrate_legacy_data(str(tmp_path))        # darf nicht crashen


def test_file_logging_captures_print(tmp_path):
    """setup_file_logging leitet print() in die Logdatei um (--noconsole-Ersatz)."""
    old_out, old_err, old_hook = sys.stdout, sys.stderr, sys.excepthook
    root = logging.getLogger()
    keep, old_level = root.handlers[:], root.level
    try:
        log_path = T.setup_file_logging(str(tmp_path))
        print("hello-from-test-12345")
        for h in root.handlers:
            h.flush()
        content = open(log_path, encoding="utf-8").read()
        assert "hello-from-test-12345" in content
        assert "gestartet" in content           # Startzeile geloggt
    finally:                                     # Streams/Hook/Handler zuruecksetzen
        for h in root.handlers[:]:
            if h not in keep:
                h.close()
                root.removeHandler(h)
        root.setLevel(old_level)
        sys.stdout, sys.stderr, sys.excepthook = old_out, old_err, old_hook
