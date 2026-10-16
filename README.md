# EcoWatt AI

English-only, local Streamlit household data collection and monthly electricity estimates. No API key, Gemini integration or monetary bill calculation.

## Run locally

Use Python 3.11 or newer. Open a terminal in this folder:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app.py
```

Open http://127.0.0.1:8501. On macOS/Linux replace `.venv\Scripts\python` with `.venv/bin/python`.

## Use

1. Select Apartment, Detached house / Villa or Other, and the month length (default 30 days). Enter rooms including the living room and kitchen, residents and typical daily occupancy. Enable past bill input only if known; unknown exports as JSON null, while an actual zero stays zero.
2. Review editable reference assumptions. They are deliberately illustrative assumptions, not researched averages or certified product specifications. Each appliance/mode has its own editable values. Alternatives outside a type's default mode use generic starting assumptions and should be reviewed.
3. Add any number of appliance groups. A quantity means identical units with identical usage; use separate groups for different models or schedules. Lighting quantity means bulbs. Custom devices support every input mode. Remove groups individually.
4. Check each field you know; unchecked fields show “Using estimated reference: …”. Mixed known/estimated fields are supported. Recommended energy input types appear first; open Advanced options to enable alternatives. Review Summary & export, then download JSON.
5. Open Energy Consumption for the monthly total, per-device breakdown, chart and optional past bill comparison. Every result is an estimate, including results based entirely on user-entered values.

Inputs use W with hours/day, kWh/year, kWh/cycle or kWh/100 cycles with cycles/week, Wh with full-equivalent charges/day and efficiency, or kWh/month. Ovens default to energy per cooking session and sessions/week. Power and monthly modes are also available. Monthly energy is per unit, not the whole group. No units are silently converted, and no inferred consumption is presented as measured data.

The JSON contract (v1.1) includes household, stable device IDs, quantities, input mode, field values and provenance, estimate flags, a full reference snapshot and energy estimates. Machine values retain full calculation precision; the screen rounds results to one decimal kWh. Refrigerators and thermostatic devices should use label energy or realistic average input/time rather than assuming continuous maximum draw.

## Calculation rules

- Power: W / 1,000 × daily hours × selected days.
- Annual energy: kWh/year × selected days / 365.
- Cycle energy: kWh/cycle × weekly cycles × selected days / 7; divide kWh/100 cycles by 100 first.
- Phone: Wh / 1,000 × daily full-equivalent charges × selected days / (efficiency / 100).
- Monthly energy: entered kWh for the selected period; no extra day scaling.
- Multiply every per-unit result by quantity exactly once. Sum without intermediate rounding.

Home type, rooms, occupancy and residents describe the home; they do not automatically multiply device energy. For detached houses add pumps, outdoor lighting and other equipment as custom devices. Seasonal use is represented by the hours you enter. Unlisted appliances and standby loads are not automatically included. Compare the past bill only when period length and usage conditions match. A zero bill is valid and is never used as a percentage denominator.

See [Reference profiles](REFERENCES.md) for the representative household assumptions and their limitations.

Data lives in the current browser session; there is no database, import or automatic save. Download before closing. The server binds to localhost and Streamlit usage telemetry is disabled. Package installation requires internet; the app itself requires no external service.

## Tests

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```

Tests cover validation, defaults, provenance, structured export and Streamlit interactions. Streamlit testing follows its [official AppTest documentation](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).

Latest verification: all three ModelTests passed (including independent expected results for all six calculation modes and quantity scaling). A bare-mode smoke check rendered all five sections with every appliance type without runtime errors. Updated interactive AppTest cases are included but could not be completed in the restricted build environment because local loopback sockets were blocked; rerun the full command above on your local machine.
