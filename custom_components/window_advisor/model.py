"""Decision model. Pure: no HA imports — keep testable standalone."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal, Sequence

from . import psychro

Action = Literal["open", "close", "open_partial", "hold"]
Mode = Literal["cool", "heat", "off"]


@dataclass
class Reading:
    ts: datetime
    value: float


@dataclass
class IndoorState:
    temp_c: float
    rh_pct: float
    co2_ppm: float | None = None
    pm25: float | None = None
    voc_index: float | None = None
    nox_index: float | None = None


@dataclass
class OutdoorState:
    temp_c: float
    rh_pct: float
    pm25: float | None = None
    condition: str | None = None


@dataclass
class ForecastPoint:
    ts: datetime
    temp_c: float
    rh_pct: float
    precip_mm: float = 0.0


@dataclass
class Preferences:
    cooling_setpoint_c: float = 24.0
    heating_setpoint_c: float = 20.0
    max_outdoor_dewpoint_c: float = 16.0
    co2_threshold_ppm: float = 900.0
    co2_urgent_ppm: float = 1400.0
    outdoor_pm25_veto: float = 25.0
    pm25_ratio_buffer: float = 5.0
    horizon_h: int = 8
    hysteresis: float = 1.5


@dataclass
class Trajectory:
    slope_per_h: float
    intercept: float
    r2: float
    n: int

    def predict(self, t_h: float) -> float:
        return self.slope_per_h * t_h + self.intercept

    def cross_time_h(self, threshold: float) -> float | None:
        if abs(self.slope_per_h) < 1e-6:
            return None
        t = (threshold - self.intercept) / self.slope_per_h
        return t if t > 0 else None


@dataclass
class HourScore:
    ts: datetime
    delta_enthalpy: float
    delta_temp_c: float
    dewpoint_out_c: float
    open_score: float
    veto: str | None


@dataclass
class WindowDecision:
    action: Action
    score: float
    mode: Mode
    reasons: list[str] = field(default_factory=list)
    hourly: list[HourScore] = field(default_factory=list)
    trajectory_temp: Trajectory | None = None
    trajectory_co2: Trajectory | None = None
    horizon_h: int = 0
    next_review_h: float = 1.0


def fit_linear(readings: Sequence[Reading], now: datetime | None = None) -> Trajectory | None:
    if len(readings) < 2:
        return None
    now = now or datetime.now(timezone.utc)
    xs = [(r.ts - now).total_seconds() / 3600.0 for r in readings]
    ys = [r.value for r in readings]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    m = num / den
    b = my - m * mx
    ss_res = sum((y - (m * x + b)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return Trajectory(slope_per_h=m, intercept=b, r2=r2, n=n)


def _setpoint(mode: Mode, prefs: Preferences) -> float:
    if mode == "cool":
        return prefs.cooling_setpoint_c
    if mode == "heat":
        return prefs.heating_setpoint_c
    return (prefs.cooling_setpoint_c + prefs.heating_setpoint_c) / 2.0


def _hour_score(
    fp: ForecastPoint,
    indoor: IndoorState,
    mode: Mode,
    prefs: Preferences,
    outdoor_pm25_now: float | None,
) -> HourScore:
    h_in = psychro.enthalpy(indoor.temp_c, indoor.rh_pct)
    h_out = psychro.enthalpy(fp.temp_c, fp.rh_pct)
    dh = h_out - h_in
    setpoint = _setpoint(mode, prefs)
    dt = fp.temp_c - setpoint
    td_out = psychro.dewpoint(fp.temp_c, fp.rh_pct)

    veto: str | None = None
    if outdoor_pm25_now is not None:
        if outdoor_pm25_now > prefs.outdoor_pm25_veto:
            veto = f"outdoor_pm25={outdoor_pm25_now:.0f}>{prefs.outdoor_pm25_veto}"
        elif indoor.pm25 is not None and outdoor_pm25_now > indoor.pm25 + prefs.pm25_ratio_buffer:
            veto = f"outdoor_pm25 {outdoor_pm25_now:.0f} > indoor {indoor.pm25:.0f}+{prefs.pm25_ratio_buffer}"

    if mode == "cool" and td_out > prefs.max_outdoor_dewpoint_c and veto is None:
        veto = f"outdoor_dewpoint={td_out:.1f}>{prefs.max_outdoor_dewpoint_c}"

    if mode == "cool":
        score = -dh
    elif mode == "heat":
        score = dh
    else:
        score = -abs(dt) + abs(indoor.temp_c - setpoint)

    if veto is not None:
        score = min(score, 0.0)

    return HourScore(
        ts=fp.ts,
        delta_enthalpy=dh,
        delta_temp_c=dt,
        dewpoint_out_c=td_out,
        open_score=score,
        veto=veto,
    )


def infer_mode(outdoor_temp_c: float, prefs: Preferences) -> Mode:
    if outdoor_temp_c >= prefs.cooling_setpoint_c - 1:
        return "cool"
    if outdoor_temp_c <= prefs.heating_setpoint_c + 1:
        return "heat"
    return "off"


def decide(
    indoor: IndoorState,
    outdoor: OutdoorState,
    forecast: Sequence[ForecastPoint],
    mode: Mode | Literal["auto"] = "auto",
    prefs: Preferences | None = None,
    temp_history: Sequence[Reading] = (),
    co2_history: Sequence[Reading] = (),
    last_action: Action | None = None,
    now: datetime | None = None,
) -> WindowDecision:
    prefs = prefs or Preferences()
    now = now or datetime.now(timezone.utc)
    resolved_mode: Mode = infer_mode(outdoor.temp_c, prefs) if mode == "auto" else mode

    horizon = list(forecast)[: prefs.horizon_h]
    hourly = [
        _hour_score(fp, indoor, resolved_mode, prefs, outdoor.pm25)
        for fp in horizon
    ]

    tau = 4.0
    integral = 0.0
    weight_sum = 0.0
    for hs in hourly:
        dt_h = (hs.ts - now).total_seconds() / 3600.0
        w = math.exp(-max(dt_h, 0) / tau)
        integral += hs.open_score * w
        weight_sum += w
    avg_score = integral / weight_sum if weight_sum > 0 else 0.0

    reasons: list[str] = []
    traj_t = fit_linear(temp_history, now=now)
    traj_c = fit_linear(co2_history, now=now)

    co2_boost = 0.0
    co2_urgent = False
    if indoor.co2_ppm is not None:
        if indoor.co2_ppm >= prefs.co2_urgent_ppm:
            co2_boost = 8.0
            co2_urgent = True
            reasons.append(f"co2 urgent {indoor.co2_ppm:.0f}≥{prefs.co2_urgent_ppm}")
        elif indoor.co2_ppm >= prefs.co2_threshold_ppm:
            co2_boost = 3.0
            reasons.append(f"co2 elevated {indoor.co2_ppm:.0f}≥{prefs.co2_threshold_ppm}")
        if traj_c and traj_c.slope_per_h > 50:
            co2_boost += 2.0
            reasons.append(f"co2 rising {traj_c.slope_per_h:+.0f}ppm/h")

    near_vetoes = [hs.veto for hs in hourly[:2] if hs.veto]
    pm25_veto = any(v and "pm25" in v for v in near_vetoes)
    if near_vetoes:
        reasons.append("veto: " + "; ".join(near_vetoes[:2]))
        if pm25_veto or not co2_urgent:
            avg_score = min(avg_score, -prefs.hysteresis)
            co2_boost = 0.0

    score = avg_score + co2_boost

    if co2_urgent and not pm25_veto:
        return WindowDecision(
            action="open",
            score=score,
            mode=resolved_mode,
            reasons=["health override: urgent CO2 forces open"] + reasons,
            hourly=hourly,
            trajectory_temp=traj_t,
            trajectory_co2=traj_c,
            horizon_h=len(hourly),
            next_review_h=0.5,
        )

    if traj_t:
        target = prefs.cooling_setpoint_c if resolved_mode == "cool" else prefs.heating_setpoint_c
        cross = traj_t.cross_time_h(target)
        if cross is not None and cross < prefs.horizon_h:
            reasons.append(f"indoor T crosses {target}°C in ~{cross:.1f}h (slope {traj_t.slope_per_h:+.2f}°/h)")

    threshold = prefs.hysteresis
    if last_action == "open":
        threshold = -prefs.hysteresis
    elif last_action == "close":
        threshold = prefs.hysteresis

    if score > threshold:
        action: Action = "open"
        reasons.insert(0, f"open: score {score:+.2f} > {threshold:+.2f}")
    elif score < -threshold:
        action = "close"
        reasons.insert(0, f"close: score {score:+.2f} < {-threshold:+.2f}")
    else:
        action = "hold"
        reasons.insert(0, f"hold: score {score:+.2f} within ±{threshold:.2f}")

    next_review = 1.0
    if traj_t and abs(traj_t.slope_per_h) > 1.0:
        next_review = 0.5
    if near_vetoes:
        next_review = 0.5

    if hourly:
        avg_dh = sum(h.delta_enthalpy for h in hourly) / len(hourly)
        reasons.append(
            f"mode={resolved_mode} avgΔh(out-in)={avg_dh:+.2f}kJ/kg over {len(hourly)}h"
        )

    return WindowDecision(
        action=action,
        score=score,
        mode=resolved_mode,
        reasons=reasons,
        hourly=hourly,
        trajectory_temp=traj_t,
        trajectory_co2=traj_c,
        horizon_h=len(hourly),
        next_review_h=next_review,
    )
