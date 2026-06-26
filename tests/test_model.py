from datetime import datetime, timedelta, timezone

from wa_pure.model import (
    ForecastPoint, IndoorState, OutdoorState, Preferences, Reading,
    decide, fit_linear,
)


NOW = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)


def _hourly(start: datetime, temps_rh: list[tuple[float, float]]) -> list[ForecastPoint]:
    return [
        ForecastPoint(ts=start + timedelta(hours=i + 1), temp_c=t, rh_pct=rh)
        for i, (t, rh) in enumerate(temps_rh)
    ]


def test_fit_linear_recovers_slope():
    readings = [
        Reading(ts=NOW - timedelta(hours=2), value=23.0),
        Reading(ts=NOW - timedelta(hours=1), value=23.5),
        Reading(ts=NOW, value=24.0),
    ]
    fit = fit_linear(readings, now=NOW)
    assert abs(fit.slope_per_h - 0.5) < 1e-6
    cross = fit.cross_time_h(25.0)
    assert cross is not None and abs(cross - 2.0) < 1e-6


def test_cool_mode_opens_when_outdoor_cooler_and_dry():
    indoor = IndoorState(temp_c=26.0, rh_pct=55.0, co2_ppm=700)
    outdoor = OutdoorState(temp_c=18.0, rh_pct=55.0, pm25=5)
    forecast = _hourly(NOW, [(18, 55), (17, 55), (17, 60), (18, 60), (19, 60), (20, 65), (22, 65), (24, 65)])
    d = decide(indoor, outdoor, forecast, mode="cool", now=NOW)
    assert d.action == "open"
    assert d.score > 0


def test_cool_mode_closes_on_muggy_outdoor():
    indoor = IndoorState(temp_c=24.0, rh_pct=50.0, co2_ppm=600)
    outdoor = OutdoorState(temp_c=22.0, rh_pct=95.0, pm25=5)
    forecast = _hourly(NOW, [(22, 95), (22, 95), (23, 95), (24, 90), (25, 85), (26, 80), (27, 75), (28, 70)])
    d = decide(indoor, outdoor, forecast, mode="cool", now=NOW)
    assert d.action in ("close", "hold")
    assert any(h.veto and "dewpoint" in h.veto for h in d.hourly)


def test_pm25_veto_blocks_open_even_when_thermally_favorable():
    indoor = IndoorState(temp_c=28.0, rh_pct=50.0, co2_ppm=700, pm25=8)
    outdoor = OutdoorState(temp_c=18.0, rh_pct=40.0, pm25=80)
    forecast = _hourly(NOW, [(18, 40)] * 8)
    d = decide(indoor, outdoor, forecast, mode="cool", now=NOW)
    assert d.action != "open"
    assert any(h.veto and "pm25" in h.veto for h in d.hourly)


def test_urgent_co2_overrides_dewpoint_veto():
    indoor = IndoorState(temp_c=24.0, rh_pct=50.0, co2_ppm=1800, pm25=8)
    outdoor = OutdoorState(temp_c=22.0, rh_pct=95.0, pm25=10)
    forecast = _hourly(NOW, [(22, 95)] * 8)
    d = decide(indoor, outdoor, forecast, mode="cool", now=NOW)
    assert d.action == "open"
    assert any("co2 urgent" in r for r in d.reasons)


def test_heat_mode_opens_when_outdoor_warmer():
    indoor = IndoorState(temp_c=18.0, rh_pct=40.0, co2_ppm=600)
    outdoor = OutdoorState(temp_c=22.0, rh_pct=40.0, pm25=5)
    forecast = _hourly(NOW, [(22, 40), (23, 40), (23, 45), (22, 50), (20, 55), (18, 60), (16, 65), (15, 70)])
    d = decide(indoor, outdoor, forecast, mode="heat", now=NOW)
    assert d.action == "open"


def test_separate_setpoints_used_per_mode():
    # Same temps; ensure mode-specific setpoint affects auto-mode inference.
    prefs = Preferences(cooling_setpoint_c=26.0, heating_setpoint_c=18.0)
    # Outdoor 25 → between heating (18) and cooling (26); should land "off"
    from wa_pure.model import infer_mode
    assert infer_mode(25.0, prefs) == "cool"  # 25 >= 26-1
    assert infer_mode(17.0, prefs) == "heat"  # 17 <= 18+1
    assert infer_mode(22.0, prefs) == "off"


def test_hysteresis_keeps_open_when_marginal():
    indoor = IndoorState(temp_c=24.0, rh_pct=55.0, co2_ppm=700)
    outdoor = OutdoorState(temp_c=23.8, rh_pct=55.0, pm25=5)
    forecast = _hourly(NOW, [(23.8, 55)] * 8)
    prefs = Preferences(hysteresis=2.0)
    d_open = decide(indoor, outdoor, forecast, mode="cool", prefs=prefs, last_action="open", now=NOW)
    d_closed = decide(indoor, outdoor, forecast, mode="cool", prefs=prefs, last_action="close", now=NOW)
    assert d_open.action in ("open", "hold")
    assert d_closed.action in ("close", "hold")


def test_trajectory_predicts_crossing():
    indoor = IndoorState(temp_c=23.0, rh_pct=50.0, co2_ppm=700)
    outdoor = OutdoorState(temp_c=20.0, rh_pct=50.0, pm25=5)
    forecast = _hourly(NOW, [(20, 50)] * 6)
    rising = [
        Reading(ts=NOW - timedelta(hours=2), value=22.0),
        Reading(ts=NOW - timedelta(hours=1), value=22.5),
        Reading(ts=NOW, value=23.0),
    ]
    d = decide(indoor, outdoor, forecast, mode="cool", temp_history=rising, now=NOW)
    assert d.trajectory_temp is not None
    assert d.trajectory_temp.slope_per_h > 0
    assert any("crosses" in r for r in d.reasons)
