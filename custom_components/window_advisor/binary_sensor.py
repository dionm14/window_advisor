"""Binary sensor: True when advisor says windows should be open. For automations."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.binary_sensor import (
    PLATFORM_SCHEMA, BinarySensorEntity,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import WindowAdvisorCoordinator

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
})


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Pair with an already-set-up sensor platform of the same name."""
    name = config[CONF_NAME]
    coordinator = hass.data.get(DOMAIN, {}).get(name)
    if coordinator is None:
        # Coordinator may not exist yet if sensor platform hasn't loaded.
        # In single-config-file setups, HA loads platforms in order; document the dependency.
        raise RuntimeError(
            f"window_advisor sensor platform '{name}' must be configured before binary_sensor"
        )
    async_add_entities([WindowsShouldBeOpen(coordinator, name)])


class WindowsShouldBeOpen(CoordinatorEntity[WindowAdvisorCoordinator], BinarySensorEntity):
    _attr_should_poll = False
    _attr_icon = "mdi:window-open"

    def __init__(self, coordinator: WindowAdvisorCoordinator, base_name: str):
        super().__init__(coordinator)
        self._attr_name = f"{base_name} Windows Should Be Open"
        slug = base_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{slug}_should_open"

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
