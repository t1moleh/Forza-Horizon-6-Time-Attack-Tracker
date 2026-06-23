"""Forza Horizon 6 "Data Out" Paket-Parsing.

Format: 324-Byte "Dash"-Paket (FH4/5/6), Little Endian. Offsets per
Reifentemperaturen (268-280) gegen echte Mitschnitte verifiziert; siehe
CONTEXT.md. Dieses Modul kapselt das Parsen, damit Recorder, Tracker und
Tests dieselbe Quelle nutzen.

WICHTIG: Bei den Open-World-Time-Attack-Circuits bleiben die Lap-Felder
(BestLap/LastLap/CurrentLap/LapNumber) durchgehend 0 - FH6 sendet die
TA-Rundenzeit NICHT ueber Data Out. Sie sind hier dokumentiert, werden fuer
Time Attack aber nicht benutzt; die Runde wird selbst aus der Position
gemessen.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

DASH_PACKET_LEN = 324

# Feste Offsets (ab Paketanfang), FH4/5/6 "Dash".
OFF_RACE_ON = 0          # s32: 1 = in der Welt aktiv, 0 = Menue/Pause
OFF_ORDINAL = 212        # s32: CarOrdinal
OFF_CLASS = 216          # s32: 0=D 1=C 2=B 3=A 4=S1 5=S2 6=R 7=X (FH6: R unter X)
OFF_PI = 220             # s32: CarPerformanceIndex
OFF_DRIVETRAIN = 224     # s32: 0=FWD 1=RWD 2=AWD

# --- Sled-Block (Offsets identisch in FH) ---
OFF_ENGINE_MAX_RPM = 8
OFF_ENGINE_IDLE_RPM = 12
OFF_CURRENT_RPM = 16
OFF_ACCEL_X = 20         # g, quer (lateral)
OFF_ACCEL_Y = 24         # g, vertikal
OFF_ACCEL_Z = 28         # g, laengs (Beschl./Bremsen)
OFF_ANG_VEL_Y = 48       # rad/s, Gierrate (Rotation -> Uebersteuern)
OFF_YAW = 56
OFF_PITCH = 60
OFF_ROLL = 64
OFF_SUSP_NORM = 68       # FL,FR,RL,RR je +4 (normierter Federweg 0..1)
OFF_SLIP_RATIO = 84      # FL.. (laengs)
OFF_SLIP_ANGLE = 164     # FL.. (quer)
OFF_COMBINED_SLIP = 180  # FL.. (Grip-Ausnutzung, >1 = ueber dem Limit)

# Dash-Block ab 244 (Sled 232 + 12 Byte Horizon-Placeholder).
_DASH = 244
OFF_POS_X = _DASH + 0    # 244 f32
OFF_POS_Y = _DASH + 4    # 248 f32 (Hoehe - fuer 2D-Messung ignoriert)
OFF_POS_Z = _DASH + 8    # 252 f32 (Bodenebene)
OFF_SPEED = _DASH + 12   # 256 f32 (m/s)
OFF_POWER = _DASH + 16   # 260 f32 (W)
OFF_TORQUE = _DASH + 20  # 264 f32 (Nm)
OFF_TIRE_TEMP = _DASH + 24   # 268 FL,FR,RL,RR je +4
OFF_BOOST = _DASH + 40   # 284 f32
OFF_FUEL = _DASH + 44    # 288 f32 (0..1)
OFF_DIST = _DASH + 48    # 292 f32 (m)
# Spielinterne Lap-Timer (im Open-World-Time-Attack = 0, in Rivals vermutlich
# befuellt -> Rivals-Probe prueft das):
OFF_BEST_LAP = _DASH + 52       # 296 f32 (s)
OFF_LAST_LAP = _DASH + 56       # 300 f32 (s)
OFF_CUR_LAP = _DASH + 60        # 304 f32 (s)
OFF_CUR_RACE_TIME = _DASH + 64  # 308 f32 (s)
OFF_LAP_NUMBER = _DASH + 68     # 312 u16
OFF_RACE_POS = _DASH + 70       # 314 u8
# Eingaben (u8/s8) am Paketende
OFF_THROTTLE = _DASH + 71   # 315 u8 (0..255)
OFF_BRAKE = _DASH + 72      # 316 u8
OFF_CLUTCH = _DASH + 73     # 317 u8
OFF_HANDBRAKE = _DASH + 74  # 318 u8
OFF_GEAR = _DASH + 75       # 319 u8
OFF_STEER = _DASH + 76      # 320 s8 (-127..127)

CLASS_NAMES = {0: "D", 1: "C", 2: "B", 3: "A", 4: "S1", 5: "S2", 6: "R", 7: "X"}
DRIVETRAIN_NAMES = {0: "FWD", 1: "RWD", 2: "AWD"}

_S32 = struct.Struct("<i")
_F32 = struct.Struct("<f")
_U16 = struct.Struct("<H")


def _u16(data: bytes, off: int) -> int:
    return _U16.unpack_from(data, off)[0]


def _s32(data: bytes, off: int) -> int:
    return _S32.unpack_from(data, off)[0]


def _f32(data: bytes, off: int) -> float:
    return _F32.unpack_from(data, off)[0]


def _u8(data: bytes, off: int) -> int:
    return data[off]


def _s8(data: bytes, off: int) -> int:
    v = data[off]
    return v - 256 if v >= 128 else v


def _wheels(data: bytes, off: int) -> dict:
    """Vier f32 (FL, FR, RL, RR) ab off als Dict."""
    return {
        "fl": round(_f32(data, off), 3),
        "fr": round(_f32(data, off + 4), 3),
        "rl": round(_f32(data, off + 8), 3),
        "rr": round(_f32(data, off + 12), 3),
    }


@dataclass(frozen=True)
class Packet:
    """Eine geparste Telemetrie-Momentaufnahme (nur die Felder, die wir nutzen)."""

    race_on: int
    ordinal: int
    car_class: int
    pi: int
    drivetrain: int
    x: float
    z: float

    @property
    def in_world(self) -> bool:
        return bool(self.race_on)

    @property
    def class_name(self) -> str:
        return CLASS_NAMES.get(self.car_class, str(self.car_class))

    @property
    def drivetrain_name(self) -> str:
        return DRIVETRAIN_NAMES.get(self.drivetrain, str(self.drivetrain))


def parse(data: bytes) -> Packet | None:
    """Parst ein Dash-Paket. Gibt None zurueck, wenn es zu kurz/ungueltig ist."""
    if len(data) < DASH_PACKET_LEN - 1:  # toleriere fehlendes letztes Byte
        return None
    return Packet(
        race_on=_s32(data, OFF_RACE_ON),
        ordinal=_s32(data, OFF_ORDINAL),
        car_class=_s32(data, OFF_CLASS),
        pi=_s32(data, OFF_PI),
        drivetrain=_s32(data, OFF_DRIVETRAIN),
        x=_f32(data, OFF_POS_X),
        z=_f32(data, OFF_POS_Z),
    )


def parse_telemetry(data: bytes) -> dict | None:
    """Reiche Live-Kanaele fuers Dashboard/Telemetrie-Pop-up und die
    Rundenanalyse. Liest dieselben 324-Byte-Pakete wie parse()."""
    if len(data) < DASH_PACKET_LEN - 1:
        return None
    speed = _f32(data, OFF_SPEED)
    return {
        "speed_kmh": round(speed * 3.6, 1),
        "rpm": round(_f32(data, OFF_CURRENT_RPM)),
        "rpm_max": round(_f32(data, OFF_ENGINE_MAX_RPM)),
        "gear": _u8(data, OFF_GEAR),
        "throttle": round(_u8(data, OFF_THROTTLE) / 255 * 100),
        "brake": round(_u8(data, OFF_BRAKE) / 255 * 100),
        "handbrake": round(_u8(data, OFF_HANDBRAKE) / 255 * 100),
        "steer": round(_s8(data, OFF_STEER) / 127 * 100),
        "accel_lat_g": round(_f32(data, OFF_ACCEL_X) / 9.80665, 2),
        "accel_long_g": round(_f32(data, OFF_ACCEL_Z) / 9.80665, 2),
        "accel_vert_g": round(_f32(data, OFF_ACCEL_Y) / 9.80665, 2),
        "yaw_rate": round(_f32(data, OFF_ANG_VEL_Y), 3),
        "power_kw": round(_f32(data, OFF_POWER) / 1000, 1),
        "torque_nm": round(_f32(data, OFF_TORQUE)),
        "boost": round(_f32(data, OFF_BOOST), 2),
        "fuel": round(_f32(data, OFF_FUEL), 3),
        "tire_temp": _wheels(data, OFF_TIRE_TEMP),
        "tire_slip": _wheels(data, OFF_COMBINED_SLIP),
        "susp_travel": _wheels(data, OFF_SUSP_NORM),
        # Fuer den Tuning-Assistenten: Slip-Ratio (laengs: Durchdrehen/Blockieren)
        # und Slip-Winkel (quer: Unter-/Uebersteuern, Setup-Balance) je Rad.
        "slip_ratio": _wheels(data, OFF_SLIP_RATIO),
        "slip_angle": _wheels(data, OFF_SLIP_ANGLE),
    }


def parse_lap_timing(data: bytes) -> dict | None:
    """Spielinterne Lap-Timer-Felder (fuer den Rivals-Modus). Im Open-World-
    Time-Attack sind diese 0 (deshalb die GPS-Stoppuhr); in Rivals vermutlich
    befuellt -> die Rivals-Probe prueft genau das."""
    if len(data) < DASH_PACKET_LEN - 1:
        return None
    return {
        "race_on": _s32(data, OFF_RACE_ON),
        "lap_number": _u16(data, OFF_LAP_NUMBER),
        "race_position": _u8(data, OFF_RACE_POS),
        "current_lap": round(_f32(data, OFF_CUR_LAP), 3),
        "last_lap": round(_f32(data, OFF_LAST_LAP), 3),
        "best_lap": round(_f32(data, OFF_BEST_LAP), 3),
        "current_race_time": round(_f32(data, OFF_CUR_RACE_TIME), 3),
        "distance": round(_f32(data, OFF_DIST), 1),
    }


def pack(
    *,
    race_on: int = 1,
    ordinal: int = 0,
    car_class: int = 0,
    pi: int = 0,
    drivetrain: int = 0,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    speed: float = 0.0,
    current_rpm: float = 0.0,
    gear: int = 0,
    throttle: int = 0,
    brake: int = 0,
    steer: int = 0,
    accel_x: float = 0.0,
    accel_z: float = 0.0,
    tire_temp: tuple = (0.0, 0.0, 0.0, 0.0),
) -> bytes:
    """Baut ein 324-Byte-Dash-Paket - fuer Tests und den Paket-Simulator."""
    buf = bytearray(DASH_PACKET_LEN)
    _S32.pack_into(buf, OFF_RACE_ON, race_on)
    _S32.pack_into(buf, OFF_ORDINAL, ordinal)
    _S32.pack_into(buf, OFF_CLASS, car_class)
    _S32.pack_into(buf, OFF_PI, pi)
    _S32.pack_into(buf, OFF_DRIVETRAIN, drivetrain)
    _F32.pack_into(buf, OFF_POS_X, x)
    _F32.pack_into(buf, OFF_POS_Y, y)
    _F32.pack_into(buf, OFF_POS_Z, z)
    _F32.pack_into(buf, OFF_SPEED, speed)
    _F32.pack_into(buf, OFF_CURRENT_RPM, current_rpm)
    _F32.pack_into(buf, OFF_ACCEL_X, accel_x)
    _F32.pack_into(buf, OFF_ACCEL_Z, accel_z)
    for i, t in enumerate(tire_temp[:4]):
        _F32.pack_into(buf, OFF_TIRE_TEMP + i * 4, t)
    buf[OFF_GEAR] = gear & 0xFF
    buf[OFF_THROTTLE] = throttle & 0xFF
    buf[OFF_BRAKE] = brake & 0xFF
    buf[OFF_STEER] = steer & 0xFF
    return bytes(buf)
