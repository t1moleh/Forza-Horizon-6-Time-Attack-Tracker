"""Tests fuer Rundenanalyse, Spur-Speicherung und den /api/lap-Loader."""
import csv

from fh6tracker import traces as tr
from fh6tracker.analysis import analyze_lap
from fh6tracker.tracker import load_lap_analysis


def _trace(lap_id, time_s, channels):
    return {"lap_id": lap_id, "car_name": "Ferrari 355", "car_ordinal": 253,
            "track": "Legend Island", "time_seconds": time_s,
            "time": "x", "channels": channels}


def _const_channels(n=100, lap_len=1000.0, speed=100.0, throttle=100, brake=0,
                    slip=0.0):
    step = lap_len / n
    ch = tr.empty_channels()
    for i in range(n + 1):
        d = i * step
        ch["dist"].append(round(d, 1))
        ch["t"].append(round(d / (speed / 3.6), 3))   # gleichmaessig
        ch["speed_kmh"].append(speed)
        ch["throttle"].append(throttle)
        ch["brake"].append(brake)
        for w in ("fl", "fr", "rl", "rr"):
            ch[f"slip_{w}"].append(slip)
    return ch


def _codes(res):
    return {s["code"] for s in res["suggestions"]}


def test_analyze_detects_coasting():
    ch = _const_channels(throttle=0, brake=0)  # nur rollen
    res = analyze_lap(_trace("a", 60.0, ch))
    assert res["stats"]["coasting_pct"] > 90
    assert "coasting" in _codes(res)


def test_analyze_detects_high_slip():
    ch = _const_channels(slip=1.5)
    res = analyze_lap(_trace("a", 60.0, ch))
    assert res["stats"]["high_slip_pct"] > 90
    assert "high_slip" in _codes(res)
    # strukturiert: code + params + text
    s = next(s for s in res["suggestions"] if s["code"] == "high_slip")
    assert "pct" in s["params"] and s["text"]


def test_delta_zones_against_faster_reference():
    fast = _trace("fast", 50.0, _const_channels(speed=120.0))   # schneller
    slow = _trace("slow", 60.0, _const_channels(speed=100.0))   # langsamer
    res = analyze_lap(slow, reference=fast)
    assert res["reference"]["lap_id"] == "fast"
    assert res["delta_zones"]                      # es gibt Verlustzonen
    assert res["delta_zones"][0]["lost_s"] > 0
    assert "delta_zone" in _codes(res)


def test_trace_save_load_roundtrip(tmp_path):
    d = str(tmp_path / "laps")
    t = _trace("lap1", 91.4, _const_channels())
    tr.save_trace(d, t)
    loaded = tr.load_trace(d, "lap1")
    assert loaded["lap_id"] == "lap1"
    assert loaded["channels"]["dist"] == t["channels"]["dist"]
    assert tr.load_trace(d, "missing") is None


def test_best_lap_id_for(tmp_path):
    log = str(tmp_path / "lap_times.csv")
    with open(log, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["auto", "strecke", "rundenzeit_s", "lap_id"])
        w.writerow(["Ferrari 355", "Legend Island", "92.5", "L1"])
        w.writerow(["Ferrari 355", "Legend Island", "91.0", "L2"])
        w.writerow(["Porsche", "Legend Island", "80.0", "L3"])
    assert tr.best_lap_id_for(log, "Ferrari 355", "Legend Island") == "L2"
    # mit Ausschluss der Bestrunde -> naechstbeste
    assert tr.best_lap_id_for(log, "Ferrari 355", "Legend Island", exclude_id="L2") == "L1"


def test_load_lap_analysis_end_to_end(tmp_path):
    paths = {"traces": str(tmp_path / "laps"), "log": str(tmp_path / "lap_times.csv")}
    tr.save_trace(paths["traces"], _trace("L2", 91.0, _const_channels(speed=110.0)))
    tr.save_trace(paths["traces"], _trace("L1", 92.5, _const_channels(speed=100.0)))
    with open(paths["log"], "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["auto", "strecke", "rundenzeit_s", "lap_id"])
        w.writerow(["Ferrari 355", "Legend Island", "92.5", "L1"])
        w.writerow(["Ferrari 355", "Legend Island", "91.0", "L2"])
    out = load_lap_analysis(paths, "L1")
    assert out is not None
    assert out["lap"]["lap_id"] == "L1"
    assert "channels" in out and "analysis" in out
    assert out["analysis"]["reference"]["lap_id"] == "L2"   # schnellere Runde
    assert load_lap_analysis(paths, "nope") is None
