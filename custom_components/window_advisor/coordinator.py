"""Coordinator: pull HA state + forecast + history, run decide(), share with entities."""
from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.recorder import history, get_instance
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_CO2_THRESHOLD, CONF_CO2_URGENT, CONF_COOLING_SETPOINT,
    CONF_HEATING_SETPOINT, CONF_HISTORY_HOURS, CONF_HORIZON_HOURS,
    CONF_HYSTERESIS, CONF_INDOOR_CO2, CONF_INDOOR_HUMIDITY, CONF_INDOOR_NOX,
    CONF_INDOOR_PM25, CONF_INDOOR_TEMP, CONF_INDOOR_VOC, CONF_MAX_OUTDOOR_DEWPOINT,
    CONF_MODE, CONF_OUTDOOR_PM25, CONF_OUTDOOR_PM25_VETO, CONF_PM25_RATIO_BUFFER,
    CONF_WEATHER, LAST_ACTION_KEY,
)
from .model import (
    ForecastPoint, IndoorState, OutdoorState, Preferences, Reading,
    WindowDecision, decide,
)
from .psychro import to_celsius

_LOGGER = logging.getLogger(__name__)


def _state_float(s: State | None) -> float | None:
    if s is None or s.state in ("unknown", "unavailable", "", None):
        return None
    try:
        return float(s.state)
    except (TypeError, ValueError):
        return None


def _state_unit(s: State | None) -> str | None:
    if s is None:
        return None
    return s.attributes.get("unit_of_measurement")


class WindowAdvisorCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        config: dict[str, Any],
        scan_interval: timedelta,
    ):
        super().__init__(hass, _LOGGER, name=name, update_interval=scan_interval)
        self._cfg = config
        self._last_action: str | None = None

        self._prefs = Preferences(
            cooling_setpoint_c=config.get(CONF_COOLING_SETPOINT, 24.0),
            heating_setpoint_c=config.get(CONF_HEATING_SETPOINT, 20.0),
            max_outdoor_dewpoint_c=config.get(CONF_MAX_OUTDOOR_DEWPOINT, 16.0),
            co2_threshold_ppm=config.get(CONF_CO2_THRESHOLD, 900.0),
            co2_urgent_ppm=config.get(CONF_CO2_URGENT, 1400.0),
            outdoor_pm25_veto=config.get(CONF_OUTDOOR_PM25_VETO, 25.0),
            pm25_ratio_buffer=config.get(CONF_PM25_RATIO_BUFFER, 5.0),
            horizon_h=int(config.get(CONF_HORIZON_HOURS, 8)),
            hysteresis=float(config.get(CONF_HYSTERESIS, 1.5)),
        )
        self._history_hours = int(config.get(CONF_HISTORY_HOURS, 2))
        self._mode = config.get(CONF_MODE, "auto")

    @property
    def prefs(self) -> Preferences:
        return self._prefs

    @property
    def last_action(self) -> str | None:
        return self._last_action

    def set_last_action(self, action: str) -> None:
        self._last_action = action

    async def _async_update_data(self) -> dict[str, Any]:
        cfg = self._cfg
        hass = self.hass

        def get(eid_key: str) -> State | None:
            eid = cfg.get(eid_key)
            return hass.states.get(eid) if eid else None

        s_temp = get(CONF_INDOOR_TEMP)
        s_rh = get(CONF_INDOOR_HUMIDITY)
        s_co2 = get(CONF_INDOOR_CO2)
        s_pm25_in = get(CONF_INDOOR_PM25)
        s_voc = get(CONF_INDOOR_VOC)
        s_nox = get(CONF_INDOOR_NOX)
        s_pm25_out = get(CONF_OUTDOOR_PM25)
        s_weather = get(CONF_WEATHER)

        if s_weather is None:
            # Likely a startup race — weather integration hasn't registered the
            # entity yet. Log + return last data (or empty) so we retry next cycle
            # instead of locking entities into "unavailable".
            _LOGGER.warning(
                "Weather entity %s not found yet; retrying next cycle. "
                "Currently registered weather.*: %s",
                cfg.get(CONF_WEATHER),
                sorted(
                    s.entity_id for s in self.hass.states.async_all()
                    if s.entity_id.startswith("weather.")
                ),
            )
            return self.data or {"decision": None, "indoor": None, "outdoor": None}

        wattrs = s_weather.attributes
        weather_unit = wattrs.get("temperature_unit")
        indoor_unit = _state_unit(s_temp)

        indoor = IndoorState(
            temp_c=to_celsius(_state_float(s_temp), indoor_unit) or 22.0,
            rh_pct=_state_float(s_rh) or 50.0,
            co2_ppm=_state_float(s_co2),
            pm25=_state_float(s_pm25_in),
            voc_index=_state_float(s_voc),
            nox_index=_state_float(s_nox),
        )
        outdoor = OutdoorState(
            temp_c=to_celsius(_get_float(wattrs.get("temperature")), weather_unit) or 15.0,
            rh_pct=_get_float(wattrs.get("humidity")) or 60.0,
            pm25=_state_float(s_pm25_out),
            condition=s_weather.state,
        )

        forecast = await self._fetch_forecast(cfg[CONF_WEATHER], weather_unit)
        temp_hist = await self._fetch_history(
            cfg.get(CONF_INDOOR_TEMP), convert_unit=indoor_unit
        )
        co2_hist = await self._fetch_history(cfg.get(CONF_INDOOR_CO2))

        decision = decide(
            indoor=indoor,
            outdoor=outdoor,
            forecast=forecast,
            mode=self._mode,
            prefs=self._prefs,
            temp_history=temp_hist,
            co2_history=co2_hist,
            last_action=self._last_action,
        )
        self._last_action = decision.action

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "indoor": _serialize(indoor),
            "outdoor": _serialize(outdoor),
            "decision": _serialize(decision),
        }

    async def _fetch_forecast(
        self, weather_entity: str, weather_unit: str | None
    ) -> list[ForecastPoint]:
        try:
            res = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": weather_entity, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
        except Exception as e:
            _LOGGER.warning("forecast service failed: %s", e)
            return []
        block = (res or {}).get(weather_entity) or {}
        raw = block.get("forecast", []) or []
        out: list[ForecastPoint] = []
        for f in raw:
            t = _get_float(f.get("temperature"))
            rh = _get_float(f.get("humidity"))
            dt = f.get("datetime")
            if t is None or rh is None or not dt:
                continue
            out.append(
                ForecastPoint(
                    ts=_parse_iso(dt),
                    temp_c=to_celsius(t, weather_unit) or t,
                    rh_pct=rh,
                    precip_mm=_get_float(f.get("precipitation")) or 0.0,
                )
            )
        return out

    async def _fetch_history(
        self, entity_id: str | None, convert_unit: str | None = None
    ) -> list[Reading]:
        if not entity_id:
            return []
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=self._history_hours)
        recorder = get_instance(self.hass)
        states_map = await recorder.async_add_executor_job(
            history.state_changes_during_period, self.hass, start, end, entity_id
        )
        rows = states_map.get(entity_id, []) or []
        out: list[Reading] = []
        for st in rows:
            try:
                v = float(st.state)
            except (TypeError, ValueError):
                continue
            if convert_unit:
                converted = to_celsius(v, convert_unit)
                if converted is not None:
                    v = converted
            out.append(Reading(ts=st.last_changed, value=v))
        return out


def _get_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _serialize(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: _serialize(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(x) for x in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj
