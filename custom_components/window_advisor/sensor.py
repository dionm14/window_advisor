"""Sensor entities for Window Advisor (config-entry based)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WindowAdvisorCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: WindowAdvisorCoordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.title
    async_add_entities([
        WindowAdvisorActionSensor(coordinator, entry, name),
        WindowAdvisorScoreSensor(coordinator, entry, name),
        WindowAdvisorModeSensor(coordinator, entry, name),
        WindowAdvisorTempSlopeSensor(coordinator, entry, name),
        WindowAdvisorCO2SlopeSensor(coordinator, entry, name),
    ])


class _Base(CoordinatorEntity[WindowAdvisorCoordinator], SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WindowAdvisorCoordinator,
        entry: ConfigEntry,
        base_name: str,
        key: str,
        label: str,
    ):
        super().__init__(coordinator)
        self._entry = entry
        self._key = key
        self._attr_name = label
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": base_name,
            "manufacturer": "window_advisor",
            "model": "Decision engine",
        }

    @property
    def _decision(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get("decision")


class WindowAdvisorActionSensor(_Base):
    _attr_icon = "mdi:window-open-variant"

    def __init__(self, coordinator, entry, base_name):
        super().__init__(coordinator, entry, base_name, "action", "Action")

    @property
    def native_value(self) -> str | None:
        d = self._decision
        return d["action"] if d else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        d = data.get("decision") or {}
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

    def __init__(self, coordinator, entry, base_name):
        super().__init__(coordinator, entry, base_name, "score", "Score")

    @property
    def native_value(self) -> float | None:
        d = self._decision
        return round(d["score"], 2) if d else None


class WindowAdvisorModeSensor(_Base):
    _attr_icon = "mdi:thermostat-auto"

    def __init__(self, coordinator, entry, base_name):
        super().__init__(coordinator, entry, base_name, "mode", "Mode")

    @property
    def native_value(self) -> str | None:
        d = self._decision
        return d["mode"] if d else None


class WindowAdvisorTempSlopeSensor(_Base):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "°C/h"
    _attr_icon = "mdi:trending-up"

    def __init__(self, coordinator, entry, base_name):
        super().__init__(coordinator, entry, base_name, "temp_slope", "Indoor Temp Slope")

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

    def __init__(self, coordinator, entry, base_name):
        super().__init__(coordinator, entry, base_name, "co2_slope", "Indoor CO2 Slope")

    @property
    def native_value(self) -> float | None:
        d = self._decision or {}
        traj = d.get("trajectory_co2")
        if not traj:
            return None
        return round(traj["slope_per_h"], 1)
