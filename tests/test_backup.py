"""Tests fuer Export/Import der Nutzerdaten (Backup ueber Updates hinweg)."""
import io
import os
import zipfile

from fh6tracker import backup


def _make_data(d):
    (d / "lap_times.csv").write_text("zeit\n95.1\n", encoding="utf-8")
    (d / "circuits.csv").write_text("name\nLegend Island\n", encoding="utf-8")
    laps = d / "laps"
    laps.mkdir()
    (laps / "x1.json").write_text("{}", encoding="utf-8")


def test_export_contains_data_and_traces(tmp_path):
    _make_data(tmp_path)
    blob = backup.export_zip(str(tmp_path))
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = set(z.namelist())
    assert "lap_times.csv" in names
    assert "circuits.csv" in names
    assert "laps/x1.json" in names


def test_export_import_roundtrip(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _make_data(src)
    blob = backup.export_zip(str(src))

    dst = tmp_path / "dst"
    dst.mkdir()
    assert backup.import_zip(str(dst), blob) is True
    assert (dst / "lap_times.csv").read_text(encoding="utf-8").strip().endswith("95.1")
    assert (dst / "circuits.csv").exists()
    assert (dst / "laps" / "x1.json").exists()


def test_import_blocks_path_traversal(tmp_path):
    # Boeses ZIP mit ../-Eintrag darf NICHT ausserhalb data_dir schreiben.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.csv", "pwned")
        z.writestr("lap_times.csv", "ok\n")
    dst = tmp_path / "dst"
    dst.mkdir()
    backup.import_zip(str(dst), buf.getvalue())
    assert not (tmp_path / "evil.csv").exists()       # Traversal verhindert
    assert (dst / "lap_times.csv").exists()           # gueltige Datei uebernommen


def test_import_bad_zip_returns_false(tmp_path):
    assert backup.import_zip(str(tmp_path), b"not a zip") is False
    assert backup.import_zip(str(tmp_path), b"") is False
