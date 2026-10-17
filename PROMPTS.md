# Prompt design (EcoWatt AI)

Model: Google Gemini (`gemini-3.8-flash` by default) through the official `google-genai` Python SDK. Full prompt text: [`prompts.py`](prompts.py). Prompt version: 1.0.

## What is sent

`ai.build_ai_input()` sends a compact JSON: household (home type, period length, rooms, residents, hours at home, optional past bill), the total monthly kWh, and each appliance group sorted by consumption with `id`, `type`, `name`, `quantity`, `input_mode`, `monthly_kwh`, `share_pct` and its inputs (value, unit label, maximum, and whether the value is `user_provided` or a `reference_estimate`). The reference-assumption snapshot is not sent; it is not needed and would only add noise.

## Techniques and why

| Technique | Where | Reason |
|---|---|---|
| Role + explicit rules (zero-shot) | `SYSTEM_INSTRUCTION` | Fixes the task (SDG 7.3 efficiency assistant) and the hard limits: use only given data, never compute kWh, change one field per suggestion, no unsafe advice, treat appliance names as labels. |
| Step-by-step reasoning (chain-of-thought) | `REASONING_STEPS` | Rank consumers → check provenance → pick a realistic field → pick a value within limits → prefer different appliances → write. The model reasons internally and outputs only JSON, so the reasoning does not clutter the answer. |
| One worked example (few-shot) | `FEW_SHOT_EXAMPLE` | Shows the expected realism (3 → 2 h/day, not 3 → 0), tone, and how to mention that a value is only an estimate. It uses a different household and a fake ID so it cannot be copied into the answer. |
| Structured output (JSON schema) | `ai.response_schema()` | Built per request. `device_id` and `field` are enums of what really exists, `proposed_value` must be ≥ 0 and at most 3 suggestions are allowed. This removes most hallucinated IDs and makes the reply machine-checkable. |

## Why Gemini does not calculate savings

Language models make arithmetic and unit mistakes. Gemini only returns `device_id`, `field` and `proposed_value`; `core.potential_saving()` computes current kWh, scenario kWh and saving with the same formulas as the rest of the app. A suggestion is discarded when it is invalid for that field (e.g. 25 h/day, 0 % charging efficiency), does not reduce consumption, would switch an appliance off completely, repeats the same field, or refers to an unknown device. Rejected items are listed in the UI for transparency.

## Ethics: where the tool can be wrong and how risk is reduced

| Risk | Mitigation |
|---|---|
| Wrong numbers | All kWh from deterministic, unit-tested code; Gemini numbers are never shown as results. |
| Hallucinated appliances/fields | JSON-schema enums plus server-side validation. |
| Unsafe advice (fridge, heating/cooling for vulnerable people) | Rule 5 in the system instruction; zero-consumption proposals rejected; safety reminder under every analysis; changes above 50 % flagged. |
| Advice built on guessed values | Each input carries provenance; the prompt asks the model to say when a value is an estimate and the UI marks such suggestions. |
| Stale advice | The analysis stores a SHA-256 fingerprint of the input data and is shown as **Out of date** once anything changes. |
| Privacy | Nothing is sent until the user confirms a checkbox and presses the button; no names or addresses are requested; the API key stays in the session or local secrets. |
| Prompt injection via appliance names | Names are declared as labels only, and the output schema cannot express anything except the allowed fields. |
| Bias / non-applicability | Reference values are generic household assumptions, not country- or income-specific data; the README and UI say they must be reviewed. Elderly people, infants and people with health needs are named explicitly in the safety guidance. |
