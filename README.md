# window_advisor — Home Assistant custom integration

Tells you (and your TRMNL display) when to open / close the windows for best air quality and energy savings. Reads AirGradient ONE + weather forecast already in Home Assistant; runs psychrometric + trajectory math; exposes the recommendation as HA entities.

## What you get

After install, these entities appear:

| Entity | What it tells you |
|---|---|
| `sensor.window_advisor_action` | `open` \| `close` \| `hold`. Attributes: score, mode, reasons, hourly forecast, trajectory slopes, full indoor/outdoor snapshot. |
| `sensor.window_advisor_score` | Numeric decision score (signed; positive = open) |
| `sensor.window_advisor_mode` | `cool` / `heat` / `off` resolved per outdoor temp |
| `sensor.window_advisor_indoor_temp_slope` | °C/h (linear fit on last N hours) |
| `sensor.window_advisor_indoor_co2_slope` | ppm/h |
| `binary_sensor.window_advisor_windows_should_be_open` | True when action == open. Use this for automations. |

## How the decision is made

For each hour in the forecast horizon (default 8h):

1. Compute moist-air **enthalpy** indoors and outdoors (Magnus-Tetens psychrometrics — `psychro.py`). Enthalpy beats raw temperature: 20°C / 95% RH carries more cooling load than 20°C / 40% RH.
2. **Score**:
   - Cool mode: open is favored when outdoor enthalpy is lower (free cooling).
   - Heat mode: open is favored when outdoor enthalpy is higher (free heating — rare; mostly solar gain).
3. **Hard vetoes**:
   - Outdoor PM2.5 above `outdoor_pm25_veto` or `pm25_ratio_buffer` above indoor.
   - Cool mode + outdoor dewpoint above `max_outdoor_dewpoint` (sticky air defeats AC dehumidification).
4. Hours weighted by `exp(-Δt/4h)` — the next hour dominates the integrated score.
5. **CO2 boost**: indoor CO2 ≥ threshold adds to score. CO2 ≥ urgent forces open unless PM2.5 vetoes (health > efficiency).
6. **Trajectory fit** (linear OLS on last 2h of indoor temp & CO2) → reports slope and predicts when indoor temp will cross the active setpoint.
7. **Hysteresis** vs. the last action prevents flip-flop.

## Install

This is a YAML-configured custom integration (no UI config flow yet — keeps install minimal).

1. Copy the `custom_components/window_advisor/` folder into your HA config dir:
   ```
   <ha_config>/custom_components/window_advisor/
   ```
   On HAOS / TrueNAS SCALE: SSH or use the File Editor add-on / Studio Code Server.
2. Paste the snippet from `config.example.yaml` into your `configuration.yaml` and edit entity IDs to match your sensors.
3. **Restart Home Assistant** (not just "reload YAML" — new integrations need a full restart).
4. Check Developer Tools → States for `sensor.window_advisor_action`.

## TRMNL integration

TRMNL's HA plugin reads any entity. Point it at `sensor.window_advisor_action`; the attributes carry everything else (reasons, score, hourly forecast). A simple template for a Mash plugin:

```liquid
{{ states.sensor.window_advisor_action.state | upcase }}
score {{ state_attr('sensor.window_advisor_action', 'score') | round(1) }}
{% for r in state_attr('sensor.window_advisor_action', 'reasons') %}- {{ r }}
{% endfor %}
```

## Automation example

```yaml
automation:
  - alias: Notify when windows should open
    trigger:
      - platform: state
        entity_id: binary_sensor.window_advisor_windows_should_be_open
        to: "on"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "Open the windows"
          message: >
            {{ state_attr('sensor.window_advisor_action', 'reasons') | join(' · ') }}
```

## Repo layout

```
custom_components/window_advisor/
  __init__.py
  manifest.json
  const.py
  coordinator.py   # async polling, recorder history, weather forecast
  sensor.py        # 5 sensors
  binary_sensor.py # windows_should_be_open
  model.py         # pure decision logic (trajectory fit + scoring + hysteresis)
  psychro.py       # enthalpy, dewpoint, wet-bulb, °F/°C/°K conversion
config.example.yaml
tests/             # pure-Python tests for psychro + model
```

## Test

```bash
python -m pytest
```

## Notes for HA on TrueNAS SCALE (port 30103)

You're on the HA Container app, not HAOS. The config dir lives in the app's persistent storage — usually `/mnt/<pool>/ix-applications/releases/home-assistant/volumes/.../config/` or the path you set when installing the app. Drop `custom_components/window_advisor/` there.
