"""Gemini integration tests with a fake client: no network or API key needed."""
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ai
from core import payload
from google.genai import errors
from streamlit.testing.v1 import AppTest


def device(uid, kind, mode, **values):
    return dict(id=uid, type=kind, name=kind, quantity=1, input_mode=mode, contains_estimates=True,
                inputs={k: {'value': float(v), 'source': 'reference_estimate', 'reference_key': None} for k, v in values.items()})


HOUSEHOLD = dict(home_type='Apartment', month_days=30, rooms_including_living_room_and_kitchen=3,
                 residents=2, hours_at_home_per_day=14.0, past_bill_monthly_kwh=None)
DEVICES = [device('heater', 'Electric heater', 'Power and daily use', power_w=1500, hours_per_day=3),
           device('tv', 'TV', 'Power and daily use', power_w=80, hours_per_day=4),
           device('wash', 'Washing machine', 'Energy per cycle', kwh_per_cycle=0.6, cycles_per_week=4),
           device('fridge', 'Refrigerator', 'Annual energy', kwh_per_year=250)]


def data():
    return payload(deepcopy(HOUSEHOLD), deepcopy(DEVICES), {})


def suggestion(device_id, field, value, **extra):
    return {'device_id': device_id, 'field': field, 'proposed_value': value, 'title': 'T',
            'action': 'Do it.', 'reason': 'Because.', 'cost': 'no_cost', **extra}


class FakeClient:
    def __init__(self, text=None, exc=None):
        self.text, self.exc, self.calls = text, exc, []
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls.append(dict(model=model, contents=contents, config=config))
        if self.exc:
            raise self.exc
        return SimpleNamespace(text=self.text, prompt_feedback=None)


def reply(*suggestions, analysis='Heating dominates.'):
    return json.dumps({'analysis': analysis, 'suggestions': list(suggestions)})


class AnalyzeTests(unittest.TestCase):
    def test_valid_three_suggestions_use_core_savings(self):
        client = FakeClient(reply(suggestion('heater', 'hours_per_day', 2), suggestion('tv', 'hours_per_day', 3),
                                  suggestion('wash', 'cycles_per_week', 3)))
        result = ai.analyze(data(), 'key', model='m', client=client)
        self.assertEqual(len(result['suggestions']), 3)
        self.assertAlmostEqual(result['suggestions'][0]['potential_saving_kwh'], 45)   # 1.5 kW x 1 h x 30 d
        self.assertAlmostEqual(result['suggestions'][1]['potential_saving_kwh'], 2.4)  # 0.08 kW x 1 h x 30 d
        self.assertAlmostEqual(result['suggestions'][2]['potential_saving_kwh'], 0.6 * 30 / 7)
        self.assertAlmostEqual(result['combined_saving_kwh'], 47.4 + 0.6 * 30 / 7)
        self.assertEqual(result['fingerprint'], ai.fingerprint(data()))
        self.assertEqual(result['rejected'], [])
        call = client.calls[0]
        self.assertEqual(call['model'], 'm')
        self.assertEqual(call['config'].response_mime_type, 'application/json')
        schema = call['config'].response_json_schema
        self.assertEqual(set(schema['properties']['suggestions']['items']['properties']['device_id']['enum']),
                         {'heater', 'tv', 'wash', 'fridge'})
        self.assertIn('"heater"', call['contents'])
        self.assertNotIn('reference_assumptions', call['contents'])

    def test_invalid_suggestions_are_rejected(self):
        client = FakeClient(reply(suggestion('heater', 'hours_per_day', 4),       # increases use
                                  suggestion('heater', 'hours_per_day', 0),       # switches off
                                  suggestion('ghost', 'hours_per_day', 1)))       # unknown device
        result = ai.analyze(data(), 'key', client=client)
        self.assertEqual(result['suggestions'], [])
        self.assertEqual(len(result['rejected']), 3)
        self.assertIsNone(result['combined_saving_kwh'])

    def test_wrong_field_duplicate_and_bad_values(self):
        client = FakeClient(reply(suggestion('tv', 'hours_per_day', 2), suggestion('tv', 'hours_per_day', 1),
                                  suggestion('fridge', 'hours_per_day', 1)))
        result = ai.analyze(data(), 'key', client=client)
        self.assertEqual(len(result['suggestions']), 1)
        self.assertEqual(len(result['rejected']), 2)
        for bad in ('2', None, True, float('nan'), 25):
            analysis, valid, rejected = ai.validate_response(
                json.dumps({'analysis': 'a', 'suggestions': [suggestion('tv', 'hours_per_day', bad)]}), data())
            self.assertEqual(valid, [])

    def test_same_device_twice_is_not_added(self):
        client = FakeClient(reply(suggestion('heater', 'hours_per_day', 2), suggestion('heater', 'power_w', 1000)))
        result = ai.analyze(data(), 'key', client=client)
        self.assertEqual(len(result['suggestions']), 2)
        self.assertIsNone(result['combined_saving_kwh'])

    def test_more_than_three_are_capped_and_text_is_limited(self):
        long = 'x' * 5000
        client = FakeClient(reply(*[suggestion('heater', 'hours_per_day', 2, title=long)] +
                                  [suggestion('tv', 'hours_per_day', h) for h in (3, 2, 1)]))
        result = ai.analyze(data(), 'key', client=client)
        self.assertLessEqual(len(result['suggestions']) + len(result['rejected']), 3)
        self.assertEqual(len(result['suggestions'][0]['title']), ai.TEXT_LIMITS['title'])

    def test_malformed_and_empty_responses(self):
        for text in ('not json', '[]', '{"analysis": "a"}', None, ''):
            with self.subTest(text=text), self.assertRaises(ai.AnalysisError):
                ai.analyze(data(), 'key', client=FakeClient(text))

    def test_api_and_network_errors(self):
        cases = [(errors.ClientError(400, {'error': {'message': 'API key not valid.', 'status': 'INVALID_ARGUMENT'}}), 'API key'),
                 (errors.ClientError(429, {'error': {'message': 'quota', 'status': 'RESOURCE_EXHAUSTED'}}), 'quota'),
                 (errors.ClientError(404, {'error': {'message': 'not found', 'status': 'NOT_FOUND'}}), 'model'),
                 (errors.ServerError(503, {'error': {'message': 'busy', 'status': 'UNAVAILABLE'}}), 'temporarily'),
                 (TimeoutError('slow'), 'internet')]
        for exc, words in cases:
            with self.subTest(exc=exc), self.assertRaises(ai.AnalysisError) as ctx:
                ai.analyze(data(), 'key', client=FakeClient(exc=exc))
            self.assertIn(words, str(ctx.exception))

    def test_missing_key(self):
        with self.assertRaises(ai.AnalysisError):
            ai.call_gemini(data(), None)
        self.assertIsNone(ai.get_api_key('  ', {}))
        self.assertEqual(ai.get_api_key(None, {'GEMINI_API_KEY': ' s '}), 's')

    def test_fingerprint_changes_with_inputs(self):
        changed = data()
        changed['devices'][1]['inputs']['hours_per_day']['value'] = 5.0
        self.assertNotEqual(ai.fingerprint(data()), ai.fingerprint(changed))
        self.assertEqual(ai.fingerprint(data()), ai.fingerprint(data()))


class AppAnalysisTests(unittest.TestCase):
    def test_outdated_flag_in_app(self):
        app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
        app.button[0].click().run()
        exported = json.loads(app.json[-1].value)
        uid = exported['devices'][0]['id']
        result = ai.analyze(exported, 'key', client=FakeClient(reply(suggestion(uid, 'hours_per_day', 2))))
        app.session_state['ai_result'] = result
        app.run()
        self.assertFalse(app.exception)
        self.assertFalse(any('Out of date' in w.value for w in app.warning))
        self.assertTrue(any('kWh/month' in m.value for m in app.metric))
        app.number_input(key=f'{uid}:quantity').set_value(2).run()
        self.assertTrue(any('Out of date' in w.value for w in app.warning))
        self.assertTrue(app.button(key='ai_run').disabled)  # no key / no consent yet
        self.assertFalse(app.exception)


if __name__ == '__main__':
    unittest.main()
