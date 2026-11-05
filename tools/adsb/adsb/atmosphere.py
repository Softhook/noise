"""Heights from pressure and GNSS altitudes, and the speed of sound."""

from __future__ import annotations

import math

from .common import FEET


DEFAULT_SOUND_SPEED = 340.3  # At 15 °C
ISA_SEA_LEVEL_K = 288.15
LAPSE_RATE = 0.0065  # K per metre


def qnh_altitude_m(baro_ft, qnh_hpa, temp_c=None):
    """Height above sea level from pressure altitude and QNH.

    Without a temperature this assumes the standard atmosphere. With one, the height is scaled by the
    ratio of the actual to the standard mean temperature of the air below the aircraft, assuming the
    standard lapse rate. That is the usual altimeter temperature correction. It is approximate, and
    the airfield being near sea level keeps the error small.
    """
    standard = (baro_ft - 145366.45 * (1 - (qnh_hpa / 1013.25) ** 0.190284)) * FEET
    if temp_c is None:
        return standard
    half_lapse = LAPSE_RATE * standard / 2
    return standard * (temp_c + 273.15 - half_lapse) / (ISA_SEA_LEVEL_K - half_lapse)


def geometric_altitude_m(geom_ft, geoid_m):
    """Height above sea level from ADS-B geometric altitude, which is above the WGS84 ellipsoid."""
    return geom_ft * FEET - geoid_m


def sound_speed(temp_c):
    return 331.3 * math.sqrt(1 + temp_c / 273.15)
