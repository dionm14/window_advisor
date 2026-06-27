"""Config + options flow for Window Advisor.

User flow (initial install):
  Step 1: name + entity selections
  Step 2: preferences (setpoints, thresholds, etc.) — all defaulted

Options flow (Configure button after install):
  Single step combining entity changes + preferences.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_CO2_THRESHOLD, CONF_CO2_URGENT, CONF_COOLING_SETPOINT,
    CONF_HEATING_SETPOINT, CONF_HISTORY_HOURS, CONF_HORIZON_HOURS,
    CONF_HYSTERESIS, CONF_INDOOR_CO2, CONF_INDOOR_HUMIDITY, CONF_INDOOR_NOX,
    CONF_INDOOR_PM25, CONF_INDOOR_TEMP, CONF_INDOOR_VOC, CONF_MAX_OUTDOOR_DEWPOINT,
    CONF_MODE, CONF_OUTDOOR_PM25, CONF_OUTDOOR_PM25_VETO, CONF_PM25_RATIO_BUFFER,
    CONF_WEATHER, DEFAULT_NAME, DOMAIN,
)

MODE_OPTIONS = [
    {"value": "auto", "label": "Auto (infer from outdoor temp)"},
    {"value": "cool", "label": "Cooling season"},
    {"value": "heat", "label": "Heating season"},
    {"value": "off", "label": "Shoulder / off"},
]


def _entities_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Required(CONF_WEATHER, default=d.get(CONF_WEATHER)):
            EntitySelector(EntitySelectorConfig(domain="weather")),
        vol.Required(CONF_INDOOR_TEMP, default=d.get(CONF_INDOOR_TEMP)):
            EntitySelector(EntitySelectorConfig(domain="sensor", device_class="temperature")),
        vol.Required(CONF_INDOOR_HUMIDITY, default=d.get(CONF_INDOOR_HUMIDITY)):
            EntitySelector(EntitySelectorConfig(domain="sensor", device_class="humidity")),
        vol.Optional(CONF_INDOOR_CO2, default=d.get(CONF_INDOOR_CO2)):
            EntitySelector(EntitySelectorConfig(domain="sensor", device_class="carbon_dioxide")),
        vol.Optional(CONF_INDOOR_PM25, default=d.get(CONF_INDOOR_PM25)):
            EntitySelector(EntitySelectorConfig(domain="sensor", device_class="pm25")),
        vol.Optional(CONF_INDOOR_VOC, default=d.get(CONF_INDOOR_VOC)):
            EntitySelector(EntitySelectorConfig(domain="sensor")),
        vol.Optional(CONF_INDOOR_NOX, default=d.get(CONF_INDOOR_NOX)):
            EntitySelector(EntitySelectorConfig(domain="sensor")),
        vol.Optional(CONF_OUTDOOR_PM25, default=d.get(CONF_OUTDOOR_PM25)):
            EntitySelector(EntitySelectorConfig(domain="sensor", device_class="pm25")),
    })


def _prefs_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Optional(CONF_MODE, default=d.get(CONF_MODE, "auto")):
            SelectSelector(SelectSelectorConfig(options=MODE_OPTIONS, mode=SelectSelectorMode.DROPDOWN)),
        vol.Optional(CONF_COOLING_SETPOINT, default=d.get(CONF_COOLING_SETPOINT, 24.0)):
            NumberSelector(NumberSelectorConfig(min=10, max=35, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="°C")),
        vol.Optional(CONF_HEATING_SETPOINT, default=d.get(CONF_HEATING_SETPOINT, 20.0)):
            NumberSelector(NumberSelectorConfig(min=10, max=30, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="°C")),
        vol.Optional(CONF_MAX_OUTDOOR_DEWPOINT, default=d.get(CONF_MAX_OUTDOOR_DEWPOINT, 16.0)):
            NumberSelector(NumberSelectorConfig(min=5, max=25, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="°C")),
        vol.Optional(CONF_CO2_THRESHOLD, default=d.get(CONF_CO2_THRESHOLD, 900)):
            NumberSelector(NumberSelectorConfig(min=400, max=2000, step=50, mode=NumberSelectorMode.BOX, unit_of_measurement="ppm")),
        vol.Optional(CONF_CO2_URGENT, default=d.get(CONF_CO2_URGENT, 1400)):
            NumberSelector(NumberSelectorConfig(min=600, max=3000, step=50, mode=NumberSelectorMode.BOX, unit_of_measurement="ppm")),
        vol.Optional(CONF_OUTDOOR_PM25_VETO, default=d.get(CONF_OUTDOOR_PM25_VETO, 25)):
            NumberSelector(NumberSelectorConfig(min=5, max=200, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="µg/m³")),
        vol.Optional(CONF_PM25_RATIO_BUFFER, default=d.get(CONF_PM25_RATIO_BUFFER, 5)):
            NumberSelector(NumberSelectorConfig(min=0, max=50, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="µg/m³")),
        vol.Optional(CONF_HORIZON_HOURS, default=d.get(CONF_HORIZON_HOURS, 8)):
            NumberSelector(NumberSelectorConfig(min=1, max=24, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="h")),
        vol.Optional(CONF_HYSTERESIS, default=d.get(CONF_HYSTERESIS, 1.5)):
            NumberSelector(NumberSelectorConfig(min=0, max=10, step=0.1, mode=NumberSelectorMode.BOX)),
        vol.Optional(CONF_HISTORY_HOURS, default=d.get(CONF_HISTORY_HOURS, 2)):
            NumberSelector(NumberSelectorConfig(min=1, max=12, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="h")),
    })


class WindowAdvisorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Two-step user flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_NAME] = user_input.pop(CONF_NAME, DEFAULT_NAME)
            self._data.update({k: v for k, v in user_input.items() if v is not None})
            return await self.async_step_prefs()

        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        schema = vol.Schema({
            vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        }).extend(_entities_schema().schema)

        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_prefs(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=self._data.get(CONF_NAME, DEFAULT_NAME),
                data=self._data,
                options=user_input,
            )
        return self.async_show_form(step_id="prefs", data_schema=_prefs_schema())

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return WindowAdvisorOptionsFlow(entry)


class WindowAdvisorOptionsFlow(OptionsFlow):
    """Single-step options edit: entities + prefs."""

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            # Split: entity selections go to entry.data, prefs to entry.options.
            entity_keys = set(_entities_schema().schema.keys())
            # voluptuous Marker objects: unwrap to plain key strings
            entity_key_strs = {k.schema if hasattr(k, "schema") else k for k in entity_keys}

            new_data = dict(self.entry.data)
            new_options: dict[str, Any] = {}
            for k, v in user_input.items():
                if k in entity_key_strs:
                    if v is None:
                        new_data.pop(k, None)
                    else:
                        new_data[k] = v
                else:
                    new_options[k] = v

            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return self.async_create_entry(title="", data=new_options)

        current = {**self.entry.data, **self.entry.options}
        combined = vol.Schema({**_entities_schema(current).schema, **_prefs_schema(current).schema})
        return self.async_show_form(step_id="init", data_schema=combined)
