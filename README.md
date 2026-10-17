# EcoWatt AI

English-only Streamlit tool that estimates household electricity use per appliance and asks Google Gemini for a short analysis and three personal saving suggestions. Supports **UN SDG 7, target 7.3** (improve energy efficiency) for households that want to understand and reduce their consumption. No monetary bill calculation.

**Division of work:** Python calculates every kWh value. Gemini only explains the result and proposes *which input to change and to what value*; the app then recalculates the saving with `core.potential_saving()` and rejects proposals that are invalid, increase consumption, switch an appliance off completely or refer to a device/field that does not exist.

## Run locally

Use Python 3.11 or newer. Open a terminal in this folder:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app.py
```

Open http://127.0.0.1:8501. On macOS/Linux replace `.venv\Scripts\python` with `.venv/bin/python`.

### Gemini API key

Create a key in Google AI Studio, then use one of these (first match wins):

1. Type it into the password field in **Energy Consumption** (kept only in the browser session), or
2. Create `.streamlit/secrets.toml` with `GEMINI_API_KEY = "your-key"` (ignored by git), or
3. Set the environment variable `GEMINI_API_KEY`.

The default model is `gemini-3.8-flash`. Override it with the environment variable `GEMINI_MODEL` if needed. Never commit a key to the repository.

## Use

1. Select Apartment, Detached house / Villa or Other, and the month length (default 30 days). Enter rooms including the living room and kitchen, residents and typical daily occupancy. Enable past bill input only if known; unknown exports as JSON null, while an actual zero stays zero.
2. Review editable reference assumptions. They are deliberately illustrative assumptions, not researched averages or certified product specifications. Each appliance/mode has its own editable values. Alternatives outside a type's default mode use generic starting assumptions and should be reviewed.
3. Add any number of appliance groups. A quantity means identical units with identical usage; use separate groups for different models or schedules. Lighting quantity means bulbs. Custom devices support every input mode. Remove groups individually.
4. Check each field you know; unchecked fields show “Using estimated reference: …”. Mixed known/estimated fields are supported. Recommended energy input types appear first; open Advanced options to enable alternatives. Review Summary & export, then download JSON.
5. Open Energy Consumption for the monthly total, per-device breakdown, chart and optional past bill comparison. Every result is an estimate, including results based entirely on user-entered values.
6. In the same tab, enter a Gemini key if none is configured, confirm the data-sharing checkbox and select **Analyze with Gemini**. You get a 2–4 sentence analysis and up to three suggestions, each with the appliance, the changed value (current → proposed), and the saving in kWh/month calculated by the app. Suggestions on different appliances are summed into a combined saving. If you change any input afterwards, the analysis is marked **Out of date** until you run it again.

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

## AI analysis and prompts

Prompts are in [`prompts.py`](prompts.py); design reasoning is in [PROMPTS.md](PROMPTS.md). The request combines a role with explicit rules (zero-shot), internal step-by-step reasoning (chain-of-thought), one worked example (few-shot) and a JSON schema built per request so `device_id` and `field` can only take values that exist in your data.

Error handling: missing key, rejected key, unknown model, quota/rate limit, server errors, timeouts/network errors, empty or blocked answers and malformed JSON each produce a clear message instead of a crash. Two attempts are made on transient errors with a 60 s timeout.

## Privacy and data

Data lives in the current browser session; there is no database, import or automatic save. Download before closing. The server binds to localhost and Streamlit usage telemetry is disabled. Nothing is sent to Gemini until you confirm the checkbox and press the button; what is sent is the household figures, appliance list (including the names you typed), inputs with their provenance and the calculated kWh. Avoid personal information in appliance names.

## Tests

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```

Tests cover validation, defaults, provenance, structured export, Streamlit interactions and the Gemini layer. Gemini tests use a fake client, so they need neither network access nor an API key. Streamlit testing follows its [official AppTest documentation](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).

Latest verification (2026-10-17): all 21 tests passed, including the AppTest interaction cases and the out-of-date marker. A live end-to-end run with gemini-3.8-flash was verified manually: analysis, three validated suggestions with recalculated savings, the out-of-date marker after an input change, and the invalid-key error message.
