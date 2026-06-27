"""Binary sensor: windows should be open (config-entry based)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    async_add_entities([WindowsShouldBeOpen(coordinator, entry)])


class WindowsShouldBeOpen(CoordinatorEntity[WindowAdvisorCoordinator], BinarySensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:window-open"
    _attr_name = "Windows Should Be Open"

    def __init__(self, coordinator: WindowAdvisorCoordinator, entry: ConfigEntry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_should_open"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "window_advisor",
            "model": "Decision engine",
        }

    @property
    def is_on(self) -> bool | None:
        d = (self.coordinator.data or {}).get("decision")
        if not d:
            return None
        return d.get("action") == "open"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = (self.coordinator.data or {}).get("decision") or {}
        return {
            "action": d.get("action"),
            "score": d.get("score"),
            "mode": d.get("mode"),
            "reasons": d.get("reasons", []),
        }
