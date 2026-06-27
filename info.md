# Window Advisor

Tells you when to open / close windows for best air quality + energy savings. Reads AirGradient (or any indoor T/RH/CO2/PM2.5 sensors) and your weather entity, applies psychrometrics + trajectory math, exposes the recommendation as Home Assistant entities.

## After install

1. Restart Home Assistant.
2. Settings → Devices & Services → **Add Integration** → search "Window Advisor".
3. Pick your weather + indoor sensor entities; tune setpoints. Defaults are sensible.

Then watch `sensor.window_advisor_action` and `binary_sensor.window_advisor_windows_should_be_open`.

See the GitHub README for the full decision model and TRMNL integration example.
