import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import CATALOG, MODES, defaults, payload, validate, monthly_energy
from streamlit.testing.v1 import AppTest


class ModelTests(unittest.TestCase):
    def test_monthly_units_and_quantity(self):
        cases = [
            ('Power and daily use', dict(power_w=100, hours_per_day=4), 12),
            ('Annual energy', dict(kwh_per_year=365), 30),
            ('Energy per cycle', dict(kwh_per_cycle=0.7, cycles_per_week=7), 21),
            ('Energy per 100 cycles', dict(kwh_per_100_cycles=70, cycles_per_week=7), 21),
            ('Battery and charging', dict(battery_wh=20, charges_per_day=1, charging_efficiency_pct=80), 0.75),
            ('Monthly energy', dict(kwh_per_month=42), 42),
        ]
        for mode, values, expected in cases:
            d = dict(input_mode=mode, quantity=3, inputs={k: {'value': v} for k, v in values.items()})
            self.assertAlmostEqual(monthly_energy(d, 30), expected * 3)
        with self.assertRaises(ValueError):
            monthly_energy(d, 0)

    def test_all_types_and_modes(self):
        h = dict(rooms_including_living_room_and_kitchen=3, residents=2, hours_at_home_per_day=12, past_bill_monthly_kwh=None)
        for kind in CATALOG:
            for mode in MODES:
                d = dict(name=kind, quantity=2, input_mode=mode, inputs={k: {'value': v, 'source': 'reference_estimate'} for k, v in defaults(kind, mode).items()})
                self.assertEqual(validate(h, [d]), [])
                self.assertIsNone(json.loads(json.dumps(payload(h, [d], {})))['household']['past_bill_monthly_kwh'])
        self.assertEqual(defaults('Washing machine', 'Energy per 100 cycles')['kwh_per_100_cycles'], 60)
        h['hours_at_home_per_day'] = 25
        self.assertTrue(validate(h, [d]))
        h['hours_at_home_per_day'] = float('nan')
        self.assertTrue(validate(h, [d]))

    def test_invalid_device(self):
        h = dict(rooms_including_living_room_and_kitchen=1, residents=1, hours_at_home_per_day=0, past_bill_monthly_kwh=0)
        self.assertTrue(validate(h, []))
        d = dict(name='', quantity=0, input_mode='Power and daily use', inputs={'power_w': {'value': -1}, 'hours_per_day': {'value': 25}})
        self.assertEqual(len(validate(h, [d])), 4)
        with self.assertRaises(ValueError):
            payload(h, [d], {})


class InteractionTests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()

    def test_add_edit_reference_known_remove(self):
        app = self.app()
        self.assertFalse(app.exception)
        app.button[0].click().run()
        uid = app.session_state['devices'][0]['id']
        app.number_input(key=f'ref:TV:Power and daily use:power_w').set_value(95.0).run()
        self.assertFalse(app.exception)
        app.checkbox(key=f'{uid}:Power and daily use:hours_per_day:known').check().run()
        app.number_input(key=f'{uid}:Power and daily use:hours_per_day:value').set_value(2.0).run()
        app.number_input(key=f'{uid}:quantity').set_value(3).run()
        exported = json.loads(app.json[-1].value)
        self.assertEqual(exported['devices'][0]['inputs']['power_w']['value'], 95)
        self.assertEqual(exported['devices'][0]['inputs']['hours_per_day']['source'], 'user_provided')
        self.assertEqual(exported['devices'][0]['quantity'], 3)
        app.button(key=f'{uid}:remove').click().run()
        self.assertEqual(app.session_state['devices'], [])
        self.assertFalse(app.exception)

    def test_types_modes_and_optional_bill(self):
        app = self.app()
        app.checkbox(key='known_bill').check().run()
        app.number_input(key='bill').set_value(0.0).run()
        for kind in CATALOG:
            app.selectbox(key='add_kind').select(kind).run()
            app.button[0].click().run()
            self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['devices']), len(CATALOG))
        uid = app.session_state['devices'][0]['id']
        app.checkbox(key=f'{uid}:advanced').check().run()
        for mode in MODES:
            app.selectbox(key=f'{uid}:mode').select(mode).run()
            self.assertFalse(app.exception)
        self.assertEqual(json.loads(app.json[-1].value)['household']['past_bill_monthly_kwh'], 0)
        app.checkbox(key='known_bill').uncheck().run()
        self.assertIsNone(json.loads(app.json[-1].value)['household']['past_bill_monthly_kwh'])

    def test_phone_options_dwelling_and_energy(self):
        app = self.app()
        self.assertEqual(len(app.tabs), 5)
        app.selectbox(key='dwelling').select('Detached house / Villa').run()
        app.selectbox(key='add_kind').select('Phone').run()
        app.button[0].click().run()
        uid = app.session_state['devices'][0]['id']
        self.assertEqual(app.selectbox(key=f'{uid}:mode').options, ['Battery and charging'])
        app.number_input(key=f'{uid}:quantity').set_value(3).run()
        before = json.loads(app.json[-1].value)['energy_estimate']['total_kwh']
        self.assertAlmostEqual(before, 15.4 / 1000 * 30 / .85 * 3)
        app.selectbox(key='dwelling').select('Apartment').run()
        self.assertEqual(before, json.loads(app.json[-1].value)['energy_estimate']['total_kwh'])
        app.checkbox(key=f'{uid}:advanced').check().run()
        app.selectbox(key=f'{uid}:mode').select('Annual energy').run()
        app.checkbox(key=f'{uid}:advanced').uncheck().run()
        self.assertEqual(app.selectbox(key=f'{uid}:mode').value, 'Battery and charging')
        self.assertFalse(app.exception)


if __name__ == '__main__':
    unittest.main()
