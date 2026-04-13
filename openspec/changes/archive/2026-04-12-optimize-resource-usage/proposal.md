## Why

Focus-monitor's default configuration keeps the `llama3.2-vision` model (~8 GB) loaded in Ollama memory for extended periods and runs analysis cycles every 30 minutes. On a 16 GB Apple Silicon Mac this drives memory pressure into swap, degrading the user's primary development work. The analysis cadence is tuned for real-time nudges, but the primary use case — understanding time distribution across a workday — is well served by hourly sampling with immediate model unloading between cycles.

## What Changes

- **Ollama keep-alive control**: Pass an explicit `keep_alive` value in every Ollama API request so the model unloads shortly after a batch of calls completes, freeing ~8 GB of RAM between analysis cycles.
- **Config default retuning**: Adjust default intervals to fit a sampling-oriented workflow — longer analysis intervals with proportionally more screenshots per cycle to maintain full coverage of context switches.
- **Configurable keep-alive**: Expose `ollama_keep_alive` as a user-facing config key so users can tune the tradeoff between reload latency and memory pressure.

## Capabilities

### New Capabilities
- `ollama-keep-alive`: Control Ollama model residency lifetime per request, allowing the model to unload between analysis cycles.

### Modified Capabilities
- `structured-analysis`: Default config values for `analysis_interval_sec` and `screenshots_per_analysis` change to better fit hourly sampling without losing coverage of 30-minute context-switch patterns.

## Impact

- `focusmonitor/ollama.py` — add `keep_alive` field to the API payload.
- `focusmonitor/config.py` — add `ollama_keep_alive` default; adjust `analysis_interval_sec` and `screenshots_per_analysis` defaults.
- `~/.focus-monitor/config.json` — existing installs keep their saved values; only new installs pick up new defaults.
- No new dependencies. No network changes. Ollama API's `keep_alive` field is already supported by the local server.
