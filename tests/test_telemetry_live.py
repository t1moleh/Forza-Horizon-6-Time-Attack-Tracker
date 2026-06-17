"""Tests fuer die erweiterte Live-Telemetrie (parse_telemetry)."""
import pytest

from fh6tracker import telemetry as tel


def test_parse_telemetry_core_channels():
    raw = tel.pack(
        speed=50.0,            # m/s -> 180 km/h
        current_rpm=6500.0,
        gear=4,
        throttle=255,          # -> 100 %
        brake=0,
        steer=-64,             # ~ -50 %
        accel_x=9.80665,       # 1 g quer
        accel_z=-19.6133,      # -2 g laengs (Bremsen)
        tire_temp=(85.0, 86.0, 90.0, 91.0),
    )
    t = tel.parse_telemetry(raw)
    assert t is not None
    assert t["speed_kmh"] == pytest.approx(180.0)
    assert t["rpm"] == 6500
    assert t["gear"] == 4
    assert t["throttle"] == 100
    assert t["brake"] == 0
    assert t["steer"] == -50
    assert t["accel_lat_g"] == pytest.approx(1.0, abs=0.01)
    assert t["accel_long_g"] == pytest.approx(-2.0, abs=0.01)
    assert t["tire_temp"] == {"fl": 85.0, "fr": 86.0, "rl": 90.0, "rr": 91.0}


def test_parse_telemetry_rejects_short():
    assert tel.parse_telemetry(b"\x00" * 50) is None


def test_session_exposes_telemetry_when_in_world():
    from fh6tracker.session import SessionState
    sess = SessionState()
    sess.note_packet(tel.parse(tel.pack(race_on=1, ordinal=253)), lambda o: "Car")
    sess.note_telemetry({"speed_kmh": 120.0, "gear": 3})
    snap = sess.snapshot()
    assert snap["telemetry"]["speed_kmh"] == 120.0
    # im Menue (race_on=0) keine Telemetrie
    sess.note_packet(tel.parse(tel.pack(race_on=0)), lambda o: "Car")
    assert sess.snapshot()["telemetry"] is None
