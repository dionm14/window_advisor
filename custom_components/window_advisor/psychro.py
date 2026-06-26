"""Psychrometric helpers. Magnus-Tetens for vapor pressure (good to ~0.1% in -40..50°C)."""
from __future__ import annotations
import math

_A = 17.625
_B = 243.04  # °C
P_ATM = 101_325.0


def sat_vapor_pressure(t_c: float) -> float:
    return 610.94 * math.exp(_A * t_c / (t_c + _B))


def vapor_pressure(t_c: float, rh_pct: float) -> float:
    return (rh_pct / 100.0) * sat_vapor_pressure(t_c)


def humidity_ratio(t_c: float, rh_pct: float, p_atm: float = P_ATM) -> float:
    pw = vapor_pressure(t_c, rh_pct)
    return 0.621945 * pw / (p_atm - pw)


def dewpoint(t_c: float, rh_pct: float) -> float:
    if rh_pct <= 0:
        return float("-inf")
    gamma = math.log(rh_pct / 100.0) + _A * t_c / (t_c + _B)
    return _B * gamma / (_A - gamma)


def enthalpy(t_c: float, rh_pct: float, p_atm: float = P_ATM) -> float:
    """Moist-air specific enthalpy (kJ/kg dry air)."""
    w = humidity_ratio(t_c, rh_pct, p_atm)
    return 1.006 * t_c + w * (2501.0 + 1.86 * t_c)


def wet_bulb(t_c: float, rh_pct: float, p_atm: float = P_ATM) -> float:
    """Stull (2011) approximation."""
    rh = rh_pct
    return (
        t_c * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(t_c + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * (rh ** 1.5) * math.atan(0.023101 * rh)
        - 4.686035
    )


def f_to_c(t_f: float) -> float:
    return (t_f - 32.0) * 5.0 / 9.0


def to_celsius(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    if not unit:
        return value
    u = unit.strip().lower().replace("°", "").replace(" ", "")
    if u in ("c", "celsius"):
        return value
    if u in ("f", "fahrenheit"):
        return f_to_c(value)
    if u in ("k", "kelvin"):
        return value - 273.15
    return value
