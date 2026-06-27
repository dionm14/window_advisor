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

## Install (via HACS)

1. HACS → Integrations → ⋮ (top-right) → **Custom repositories**
2. Repository: `https://github.com/dionm14/window_advisor`, Category: **Integration**, Add
3. Find **Window Advisor** in the HACS list → **Download**
4. **Restart Home Assistant**
5. Settings → Devices & Services → **Add Integration** → search "Window Advisor"
6. Walk the two-step form:
   - **Entities**: pick your weather entity + indoor temp + humidity (required). CO2, PM2.5, VOC, NOx optional.
   - **Preferences**: setpoints (°C), dewpoint ceiling, CO2 thresholds, etc. Defaults are reasonable.
7. Done. Entities appear under the new device.

### Edit later

Settings → Devices & Services → **Window Advisor** → **Configure**. Adjust any entity or preference; HA reloads the integration automatically.

## Update

HACS shows "Update available" when a new release is tagged on GitHub → click → restart HA.

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
  config_flow.py   # UI install + options flow (entity selectors)
  translations/en.json
hacs.json          # HACS metadata
info.md            # shown in HACS install dialog
tests/             # pure-Python tests for psychro + model
```

## Test

```bash
python -m pytest
```

