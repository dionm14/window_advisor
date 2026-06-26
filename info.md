# Window Advisor

Tells you when to open / close windows for best air quality + energy savings. Reads AirGradient (or any indoor T/RH/CO2/PM2.5 sensors) and your weather entity, applies psychrometrics + trajectory math, exposes the recommendation as Home Assistant entities.

## After install

1. Paste the YAML from `config.example.yaml` into `configuration.yaml` (edit entity IDs).
2. Restart Home Assistant.
3. Watch `sensor.window_advisor_action` and `binary_sensor.window_advisor_windows_should_be_open`.

See README for the full decision model and TRMNL integration example.
