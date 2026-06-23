"""Test fuer parse_lap_timing (Lap-Timer-Felder, Basis der Rivals-Probe)."""
import struct

from fh6tracker import telemetry as tel


def test_parse_lap_timing_reads_fields():
    buf = bytearray(tel.DASH_PACKET_LEN)
    struct.pack_into("<i", buf, tel.OFF_RACE_ON, 1)
    struct.pack_into("<f", buf, tel.OFF_CUR_LAP, 12.5)
    struct.pack_into("<f", buf, tel.OFF_LAST_LAP, 88.123)
    struct.pack_into("<f", buf, tel.OFF_BEST_LAP, 85.0)
    struct.pack_into("<f", buf, tel.OFF_CUR_RACE_TIME, 200.0)
    struct.pack_into("<H", buf, tel.OFF_LAP_NUMBER, 3)
    struct.pack_into("<B", buf, tel.OFF_RACE_POS, 1)

    lt = tel.parse_lap_timing(bytes(buf))
    assert lt["race_on"] == 1
    assert lt["lap_number"] == 3
    assert lt["race_position"] == 1
    assert abs(lt["current_lap"] - 12.5) < 1e-3
    assert abs(lt["last_lap"] - 88.123) < 1e-3
    assert abs(lt["best_lap"] - 85.0) < 1e-3
    assert abs(lt["current_race_time"] - 200.0) < 1e-3


def test_parse_lap_timing_zero_in_time_attack():
    # Leeres Paket = wie Open-World-Time-Attack (alle Lap-Felder 0).
    lt = tel.parse_lap_timing(bytes(tel.DASH_PACKET_LEN))
    assert lt["current_lap"] == 0 and lt["last_lap"] == 0 and lt["best_lap"] == 0
    assert lt["lap_number"] == 0
