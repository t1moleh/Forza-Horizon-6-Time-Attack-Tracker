"""Tests fuer Paket-Parsing und -Bauen (Round-Trip)."""
import pytest

from fh6tracker import telemetry as tel


def test_pack_parse_roundtrip():
    raw = tel.pack(
        race_on=1, ordinal=253, car_class=3, pi=700, drivetrain=1,
        x=4267.6, z=-5273.0,
    )
    assert len(raw) == tel.DASH_PACKET_LEN
    pkt = tel.parse(raw)
    assert pkt is not None
    assert pkt.race_on == 1
    assert pkt.ordinal == 253
    assert pkt.car_class == 3
    assert pkt.pi == 700
    assert pkt.drivetrain == 1
    assert pkt.x == pytest.approx(4267.6)  # f32-Praezision
    assert pkt.z == pytest.approx(-5273.0)
    assert pkt.in_world is True
    assert pkt.class_name == "A"
    assert pkt.drivetrain_name == "RWD"


def test_parse_rejects_short_packet():
    assert tel.parse(b"\x00" * 100) is None


def test_race_off_packet():
    pkt = tel.parse(tel.pack(race_on=0))
    assert pkt is not None
    assert pkt.in_world is False
