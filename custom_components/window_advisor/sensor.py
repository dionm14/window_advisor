"""Sensor platform: main window-advisor entity + supporting numeric sensors."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA, SensorEntity, SensorStateClass,
)
from homeassistant.const import CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_CO2_THRESHOLD, CONF_CO2_URGENT, CONF_COOLING_SETPOINT,
    CONF_HEATING_SETPOINT, CONF_HISTORY_HOURS, CONF_HORIZON_HOURS,
    CONF_HYSTERESIS, CONF_INDOOR_CO2, CONF_INDOOR_HUMIDITY, CONF_INDOOR_NOX,
    CONF_INDOOR_PM25, CONF_INDOOR_TEMP, CONF_INDOOR_VOC, CONF_MAX_OUTDOOR_DEWPOINT,
    CONF_MODE, CONF_OUTDOOR_PM25, CONF_OUTDOOR_PM25_VETO, CONF_PM25_RATIO_BUFFER,
    CONF_WEATHER, DEFAULT_NAME, DEFAULT_SCAN_INTERVAL_S, DOMAIN,
)
from .coordinator import WindowAdvisorCoordinator

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required(CONF_INDOOR_TEMP): cv.entity_id,
    vol.Required(CONF_INDOOR_HUMIDITY): cv.entity_id,
    vol.Optional(CONF_INDOOR_CO2): cv.entity_id,
    vol.Optional(CONF_INDOOR_PM25): cv.entity_id,
    vol.Optional(CONF_INDOOR_VOC): cv.entity_id,
    vol.Optional(CONF_INDOOR_NOX): cv.entity_id,
    vol.Optional(CONF_OUTDOOR_PM25): cv.entity_id,
    vol.Required(CONF_WEATHER): cv.entity_id,
    vol.Optional(CONF_MODE, default="auto"): vol.In(["auto", "cool", "heat", "off"]),
    vol.Optional(CONF_COOLING_SETPOINT, default=24.0): vol.Coerce(float),
    vol.Optional(CONF_HEATING_SETPOINT, default=20.0): vol.Coerce(float),
    vol.Optional(CONF_MAX_OUTDOOR_DEWPOINT, default=16.0): vol.Coerce(float),
    vol.Optional(CONF_CO2_THRESHOLD, default=900.0): vol.Coerce(float),
    vol.Optional(CONF_CO2_URGENT, default=1400.0): vol.Coerce(float),
    vol.Optional(CONF_OUTDOOR_PM25_VETO, default=25.0): vol.Coerce(float),
    vol.Optional(CONF_PM25_RATIO_BUFFER, default=5.0): vol.Coerce(float),
    vol.Optional(CONF_HORIZON_HOURS, default=8): vol.All(int, vol.Range(min=1, max=48)),
    vol.Optional(CONF_HYSTERESIS, default=1.5): vol.Coerce(float),
    vol.Optional(CONF_HISTORY_HOURS, default=2): vol.All(int, vol.Range(min=1, max=24)),
    # CONF_SCAN_INTERVAL handled by base PLATFORM_SCHEMA (cv.time_period).
    # Accepts int seconds, "HH:MM:SS", or {seconds: N}. Default applied in setup.
})


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    name = config[CONF_NAME]
    scan = config.get(CONF_SCAN_INTERVAL) or timedelta(seconds=DEFAULT_SCAN_INTERVAL_S)
    coordinator = WindowAdvisorCoordinator(hass, name, config, scan)

    hass.data.setdefault(DOMAIN, {})[name] = coordinator

    # Defer first refresh: schedule it in the background so platform setup
    # completes before we try to read other integrations' states (avoids races
    # with weather integration startup).
    hass.async_create_task(coordinator.async_request_refresh())

    async_add_entities([
        WindowAdvisorActionSensor(coordinator, name),
        WindowAdvisorScoreSensor(coordinator, name),
        WindowAdvisorModeSensor(coordinator, name),
        WindowAdvisorTempSlopeSensor(coordinator, name),
        WindowAdvisorCO2SlopeSensor(coordinator, name),
    ])


class _Base(CoordinatorEntity[WindowAdvisorCoordinator], SensorEntity):
    _attr_should_poll = False

    def __init__(self, coordinator: WindowAdvisorCoordinator, base_name: str, key: str, label: str):
        super().__init__(coordinator)
        self._base = base_name
        self._key = key
        self._attr_name = f"{base_name} {label}"
        slug = base_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{slug}_{key}"

    @property
    def _decision(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get("decision")


class WindowAdvisorActionSensor(_Base):
    _attr_icon = "mdi:window-open-variant"

    def __init__(self, coordinator: WindowAdvisorCoordinator, base_name: str):
        super().__init__(coordinator, base_name, "action", "Action")

    @property
    def native_value(self) -> str | None:
        d = self._decision
        return d["action"] if d else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        d = data.get("decision", {})
        return {
            "score": d.get("score"),
            "mode": d.get("mode"),
            "reasons": d.get("reasons", []),
            "next_review_h": d.get("next_review_h"),
            "horizon_h": d.get("horizon_h"),
            "trajectory_temp": d.get("trajectory_temp"),
            "trajectory_co2": d.get("trajectory_co2"),
            "hourly": d.get("hourly", []),
            "indoor": data.get("indoor"),
            "outdoor": data.get("outdoor"),
            "generated_at": data.get("generated_at"),
        }


class WindowAdvisorScoreSensor(_Base):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:scale-balance"

    def __init__(self, coordinator: WindowAdvisorCoordinator, base_name: str):
        super().__init__(coordinator, base_name, "score", "Score")

    @property
    def native_value(self) -> float | None:
        d = self._decision
        return round(d["score"], 2) if d else None


class WindowAdvisorModeSensor(_Base):
    _attr_icon = "mdi:thermostat-auto"

    def __init__(self, coordinator: WindowAdvisorCoordinator, base_name: str):
        super().__init__(coordinator, base_name, "mode", "Mode")

    @property
    def native_value(self) -> str | None:
        d = self._decision
        return d["mode"] if d else None


class WindowAdvisorTempSlopeSensor(_Base):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "°C/h"
    _attr_icon = "mdi:trending-up"

    def __init__(self, coordinator: WindowAdvisorCoordinator, base_name: str):
        super().__init__(coordinator, base_name, "temp_slope", "Indoor Temp Slope")

    @property
    def native_value(self) -> float | None:
        d = self._decision or {}
        traj = d.get("trajectory_temp")
        if not traj:
            return None
        return round(traj["slope_per_h"], 3)


class WindowAdvisorCO2SlopeSensor(_Base):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "ppm/h"
    _attr_icon = "mdi:trending-up"

    def __init__(self, coordinator: WindowAdvisorCoordinator, base_name: str):
        super().__init__(coordinator, base_name, "co2_slope", "Indoor CO2 Slope")

    @property
    def native_value(self) -> float | None:
        d = self._decision or {}
        traj = d.get("trajectory_co2")
        if not traj:
            return None
        return round(traj["slope_per_h"], 1)
