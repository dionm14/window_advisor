"""Window Advisor: config-flow integration setup."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import Event, HomeAssistant

from .const import DEFAULT_SCAN_INTERVAL_S, DOMAIN
from .coordinator import WindowAdvisorCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    config = {**entry.data, **entry.options}
    coordinator = WindowAdvisorCoordinator(
        hass,
        name=entry.title,
        config=config,
        scan_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_S),
    )
    hass.data[DOMAIN][entry.entry_id] = coordinator

    async def _first_refresh(_event: Event | None = None) -> None:
        await coordinator.async_request_refresh()

    if hass.is_running:
        hass.async_create_task(_first_refresh())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _first_refresh)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
