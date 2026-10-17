import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import CATALOG, MODES, defaults, payload, validate, monthly_energy, potential_saving
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


class SavingTests(unittest.TestCase):
    def device(self, mode='Power and daily use', quantity=1, **values):
        return dict(id='device-1', quantity=quantity, input_mode=mode,
                    inputs={k: {'value': v, 'source': 'reference_estimate'} for k, v in values.items()})

    def test_heater_and_immutability(self):
        devices = [self.device(quantity=2, power_w=1500, hours_per_day=3)]
        before = deepcopy(devices)
        result = potential_saving(devices, 'device-1', 'hours_per_day', 2)
        self.assertEqual(result['current_kwh'], 270)
        self.assertEqual(result['scenario_kwh'], 180)
        self.assertEqual(result['potential_saving_kwh'], 90)
        self.assertEqual(devices, before)

    def test_other_modes(self):
        cases = [
            ('Energy per cycle', dict(kwh_per_cycle=.7, cycles_per_week=7), 'cycles_per_week', 3.5, 10.5),
            ('Energy per 100 cycles', dict(kwh_per_100_cycles=70, cycles_per_week=7), 'cycles_per_week', 3.5, 10.5),
            ('Annual energy', dict(kwh_per_year=365), 'kwh_per_year', 182.5, 15),
            ('Monthly energy', dict(kwh_per_month=40), 'kwh_per_month', 30, 10),
            ('Battery and charging', dict(battery_wh=20, charges_per_day=1, charging_efficiency_pct=80), 'charging_efficiency_pct', 100, .15),
        ]
        for mode, values, field, proposed, expected in cases:
            with self.subTest(mode=mode):
                result = potential_saving([self.device(mode, **values)], 'device-1', field, proposed)
                self.assertAlmostEqual(result['potential_saving_kwh'], expected)

    def test_zero_increase_and_period(self):
        ds = [self.device(power_w=1000, hours_per_day=3)]
        self.assertEqual(potential_saving(ds, 'device-1', 'hours_per_day', 3)['potential_saving_kwh'], 0)
        self.assertEqual(potential_saving(ds, 'device-1', 'hours_per_day', 4)['potential_saving_kwh'], -30)
        self.assertEqual(potential_saving(ds, 'device-1', 'hours_per_day', 0, 31)['potential_saving_kwh'], 93)

    def test_invalid_proposals(self):
        ds = [self.device(power_w=1500, hours_per_day=3)]
        before = deepcopy(ds)
        for value in (-1, 25, float('nan'), float('inf'), True, '2', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                potential_saving(ds, 'device-1', 'hours_per_day', value)
        for field in ('quantity', 'cycles_per_week', 'id', None):
            with self.assertRaises(ValueError):
                potential_saving(ds, 'device-1', field, 1)
        for days in (0, 32, True, 30.5):
            with self.assertRaises(ValueError):
                potential_saving(ds, 'device-1', 'hours_per_day', 2, days)
        for device_id in ('missing', '', None):
            with self.assertRaises(ValueError):
                potential_saving(ds, device_id, 'hours_per_day', 2)
        self.assertEqual(ds, before)

    def test_invalid_baselines(self):
        valid = self.device(power_w=1500, hours_per_day=3)
        bads = [[], [valid, deepcopy(valid)], [dict(valid, quantity=True)],
                [dict(valid, input_mode='unknown')], [dict(valid, inputs={})],
                [self.device(power_w=-100, hours_per_day=3)],
                [self.device('Battery and charging', battery_wh=15, charges_per_day=1, charging_efficiency_pct=0)]]
        for ds in bads:
            with self.subTest(devices=ds), self.assertRaises(ValueError):
                potential_saving(ds, 'device-1', 'hours_per_day', 2)
        phone = self.device('Battery and charging', battery_wh=15, charges_per_day=1, charging_efficiency_pct=85)
        for efficiency in (0, 101):
            with self.assertRaises(ValueError):
                potential_saving([phone], 'device-1', 'charging_efficiency_pct', efficiency)
        with self.assertRaises(ValueError):
            potential_saving([self.device(quantity=1000, power_w=1e308, hours_per_day=24)], 'device-1', 'hours_per_day', 23)


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
