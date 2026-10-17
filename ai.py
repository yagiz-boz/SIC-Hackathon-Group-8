"""Gemini analysis: compact input, API call with error handling, and strict output validation.

Gemini only proposes *which* field to change and to *what* value. Every kWh figure shown
to the user is calculated by core.potential_saving(), never by the model.
"""
import hashlib
import json
import os
from datetime import datetime, timezone

from core import MODES, potential_saving
from prompts import PROMPT_VERSION, SYSTEM_INSTRUCTION, build_user_prompt

DEFAULT_MODEL = 'gemini-3.8-flash'
TIMEOUT_MS = 60_000
MAX_SUGGESTIONS = 3
LARGE_CHANGE = 0.5  # relative reduction above which the UI flags the suggestion
TEXT_LIMITS = {'analysis': 1200, 'title': 120, 'action': 400, 'reason': 400}
COSTS = ['no_cost', 'low_cost', 'investment']


class AnalysisError(Exception):
    """Error with a message that is safe to show to the user."""


def fingerprint(data):
    """Stable hash of the exported data; a different hash means the analysis is outdated."""
    raw = json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def build_ai_input(data):
    """Only what the analysis needs: no reference snapshot, no notes."""
    est = data['energy_estimate']
    total = est['total_kwh']
    kwh = {r['id']: r['monthly_kwh'] for r in est['devices']}
    devices = []
    for d in data['devices']:
        inputs = {}
        for key, label, _, maximum in MODES[d['input_mode']]:
            entry = {'label': label, 'value': d['inputs'][key]['value'], 'source': d['inputs'][key]['source']}
            if maximum is not None:
                entry['max'] = maximum
            inputs[key] = entry
        devices.append({'id': d['id'], 'type': d['type'], 'name': d['name'], 'quantity': d['quantity'],
                        'input_mode': d['input_mode'], 'monthly_kwh': round(kwh[d['id']], 3),
                        'share_pct': round(kwh[d['id']] / total * 100, 1) if total > 0 else 0.0,
                        'inputs_are_per_unit': True, 'inputs': inputs})
    devices.sort(key=lambda d: d['monthly_kwh'], reverse=True)
    h = data['household']
    return {'household': {'home_type': h.get('home_type'), 'month_days': est['month_days'],
                          'rooms': h['rooms_including_living_room_and_kitchen'], 'residents': h['residents'],
                          'hours_at_home_per_day': h['hours_at_home_per_day'],
                          'past_bill_kwh': h['past_bill_monthly_kwh']},
            'total_monthly_kwh': round(total, 3), 'devices': devices}


def response_schema(data):
    ids = [d['id'] for d in data['devices']]
    fields = sorted({key for d in data['devices'] for key, *_ in MODES[d['input_mode']]})
    text = {'type': 'string'}
    return {'type': 'object', 'properties': {
        'analysis': {'type': 'string', 'description': '2-4 sentence plain-language summary.'},
        'suggestions': {'type': 'array', 'minItems': 1, 'maxItems': MAX_SUGGESTIONS, 'items': {
            'type': 'object', 'properties': {
                'device_id': {'type': 'string', 'enum': ids},
                'field': {'type': 'string', 'enum': fields},
                'proposed_value': {'type': 'number', 'minimum': 0},
                'title': text, 'action': text, 'reason': text,
                'cost': {'type': 'string', 'enum': COSTS}},
            'required': ['device_id', 'field', 'proposed_value', 'title', 'action', 'reason', 'cost']}}},
        'required': ['analysis', 'suggestions']}


def get_api_key(session_key=None, secrets=None):
    """Session input first, then Streamlit secrets, then the GEMINI_API_KEY environment variable."""
    for value in (session_key, (secrets or {}).get('GEMINI_API_KEY'), os.environ.get('GEMINI_API_KEY')):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _make_client(api_key):
    from google import genai
    from google.genai import types
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(
        timeout=TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=2)))


def _api_error_message(exc):
    code = getattr(exc, 'code', None)
    text = (getattr(exc, 'message', None) or '').lower()
    if code in (401, 403) or (code == 400 and 'api key' in text):
        return 'Gemini rejected the API key. Check that the key is correct and enabled.'
    if code == 404:
        return 'The selected Gemini model was not found. Set GEMINI_MODEL to an available model.'
    if code == 429:
        return 'Gemini quota or rate limit reached. Wait a minute and try again.'
    if code is not None and code >= 500:
        return 'Gemini is temporarily unavailable. Try again shortly.'
    return f'Gemini request failed (HTTP {code}).'


def call_gemini(data, api_key, model=None, client=None):
    """Return the raw JSON text produced by Gemini. Raises AnalysisError on any failure."""
    if not api_key and client is None:
        raise AnalysisError('No Gemini API key. Enter one or set GEMINI_API_KEY.')
    from google.genai import errors, types
    model = model or os.environ.get('GEMINI_MODEL') or DEFAULT_MODEL
    prompt = build_user_prompt(json.dumps(build_ai_input(data), indent=1))
    config = types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION,
                                         response_mime_type='application/json',
                                         response_json_schema=response_schema(data))
    try:
        client = client or _make_client(api_key)
        response = client.models.generate_content(model=model, contents=prompt, config=config)
    except errors.APIError as exc:
        raise AnalysisError(_api_error_message(exc)) from exc
    except Exception as exc:  # network, timeout, DNS, TLS ...
        raise AnalysisError(f'Could not reach Gemini ({type(exc).__name__}). Check your internet connection.') from exc
    text = getattr(response, 'text', None)
    if not text:
        feedback = getattr(response, 'prompt_feedback', None)
        reason = getattr(feedback, 'block_reason', None)
        raise AnalysisError(f'Gemini returned no answer{f" (blocked: {reason})" if reason else ""}. Try again.')
    return text, model


def _clean_text(value, limit):
    return ' '.join(str(value).split())[:limit] if isinstance(value, str) else ''


def validate_response(text, data):
    """Parse Gemini JSON and keep only suggestions that the deterministic model accepts."""
    try:
        raw = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AnalysisError('Gemini returned malformed data. Try again.') from exc
    if not isinstance(raw, dict) or not isinstance(raw.get('suggestions'), list):
        raise AnalysisError('Gemini response did not follow the expected format. Try again.')
    analysis = _clean_text(raw.get('analysis'), TEXT_LIMITS['analysis'])
    by_id = {d['id']: d for d in data['devices']}
    days = data['energy_estimate']['month_days']
    valid, rejected, seen = [], [], set()
    for item in raw['suggestions'][:MAX_SUGGESTIONS]:
        if not isinstance(item, dict):
            rejected.append({'reason': 'Not an object.'})
            continue
        device_id, field = item.get('device_id'), item.get('field')
        value = item.get('proposed_value')
        if isinstance(value, int) and not isinstance(value, bool):
            value = float(value)
        try:
            if (device_id, field) in seen:
                raise ValueError('Duplicate suggestion for the same field.')
            result = potential_saving(data['devices'], device_id, field, value, days)
            if result['potential_saving_kwh'] <= 0:
                raise ValueError('Proposed value does not reduce consumption.')
            if result['scenario_kwh'] <= 0:
                raise ValueError('Proposed value would switch the appliance off completely.')
        except ValueError as exc:
            rejected.append({'device_id': device_id, 'field': field, 'proposed_value': value, 'reason': str(exc)})
            continue
        seen.add((device_id, field))
        device = by_id[device_id]
        label = next(lbl for key, lbl, *_ in MODES[device['input_mode']] if key == field)
        cost = item.get('cost') if item.get('cost') in COSTS else 'no_cost'
        valid.append({**result, 'device_name': device['name'], 'device_type': device['type'],
                      'field_label': label, 'cost': cost,
                      'value_source': device['inputs'][field]['source'],
                      'large_change': result['potential_saving_kwh'] / result['current_kwh'] > LARGE_CHANGE,
                      **{k: _clean_text(item.get(k), TEXT_LIMITS[k]) for k in ('title', 'action', 'reason')}})
    if not analysis and not valid:
        raise AnalysisError('Gemini returned no usable analysis. Try again.')
    return analysis, valid, rejected


def combined_saving(suggestions):
    """Savings can be added only if no appliance group appears twice (scenarios would overlap)."""
    ids = [s['device_id'] for s in suggestions]
    if not ids or len(ids) != len(set(ids)):
        return None
    return sum(s['potential_saving_kwh'] for s in suggestions)


def analyze(data, api_key, model=None, client=None):
    text, used_model = call_gemini(data, api_key, model, client)
    analysis, suggestions, rejected = validate_response(text, data)
    return {'analysis': analysis, 'suggestions': suggestions, 'rejected': rejected,
            'combined_saving_kwh': combined_saving(suggestions),
            'total_kwh': data['energy_estimate']['total_kwh'],
            'fingerprint': fingerprint(data), 'model': used_model, 'prompt_version': PROMPT_VERSION,
            'created_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}

