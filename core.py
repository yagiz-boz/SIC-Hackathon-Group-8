"""Validated appliance inputs and transparent monthly energy estimates."""
import math

MODES = {
    'Power and daily use': [('power_w', 'Average operating power (W)', 100.0, None), ('hours_per_day', 'Usage per day (hours)', 3.0, 24.0)],
    'Annual energy': [('kwh_per_year', 'Annual energy (kWh/year)', 250.0, None)],
    'Energy per cycle': [('kwh_per_cycle', 'Energy per cycle (kWh/cycle)', 0.8, None), ('cycles_per_week', 'Cycles per week', 3.0, None)],
    'Energy per 100 cycles': [('kwh_per_100_cycles', 'Energy per 100 cycles (kWh/100 cycles)', 80.0, None), ('cycles_per_week', 'Cycles per week', 3.0, None)],
    'Battery and charging': [('battery_wh', 'Battery capacity (Wh)', 15.0, None), ('charges_per_day', 'Full-equivalent charges per day', 1.0, None), ('charging_efficiency_pct', 'Charging efficiency (%)', 85.0, 100.0)],
    'Monthly energy': [('kwh_per_month', 'Energy per month (kWh/month)', 10.0, None)],
}
CATALOG = {
    'TV': ('Power and daily use', 80, 4),
    'Laptop': ('Power and daily use', 50, 5),
    'Desktop computer': ('Power and daily use', 200, 5),
    'Refrigerator': ('Annual energy', 250, None),
    'Gaming console': ('Power and daily use', 150, 2),
    'Air conditioner': ('Power and daily use', 1000, 4),
    'Electric heater': ('Power and daily use', 1500, 3),
    'Oven': ('Energy per cycle', 1, 3),
    'Washing machine': ('Energy per cycle', 0.6, 4),
    'Dishwasher': ('Energy per cycle', 0.8, 5),
    'Phone': ('Battery and charging', 15.4, 1),
    'Lighting': ('Power and daily use', 9, 5),
    'Custom device': ('Power and daily use', 100, 3),
}

# Representative household profiles, not market-share averages or product measurements.
PROFILES = {
    'TV': 'Medium-size LED television', 'Laptop': 'Everyday notebook computer',
    'Desktop computer': 'Everyday desktop with monitor', 'Refrigerator': 'Modern medium-size fridge-freezer',
    'Gaming console': 'Home console during gameplay', 'Air conditioner': 'Single-room split air conditioner',
    'Electric heater': 'Portable resistance heater', 'Oven': 'Electric oven, one cooking session',
    'Washing machine': 'Standard household washing machine, one wash',
    'Dishwasher': 'Standard household dishwasher, one wash',
    'Phone': 'Smartphone with approximately 4,000 mAh battery at 3.85 V',
    'Lighting': 'One LED bulb', 'Custom device': 'Generic device; review before calculating',
}

def recommended_modes(kind):
    if kind in ('Washing machine', 'Dishwasher'):
        return ['Energy per cycle', 'Energy per 100 cycles']
    return [CATALOG[kind][0]]

def monthly_energy(device, days=30):
    """Per-unit inputs; quantity applied once. Annual values use a 365-day year."""
    if not isinstance(days, int) or not 1 <= days <= 31:
        raise ValueError('Month length must be between 1 and 31 days.')
    v = {k: field['value'] for k, field in device['inputs'].items()}
    mode = device['input_mode']
    if mode == 'Power and daily use':
        energy = v['power_w'] / 1000 * v['hours_per_day'] * days
    elif mode == 'Annual energy':
        energy = v['kwh_per_year'] * days / 365
    elif mode in ('Energy per cycle', 'Energy per 100 cycles'):
        cycle = v['kwh_per_cycle'] if mode == 'Energy per cycle' else v['kwh_per_100_cycles'] / 100
        energy = cycle * v['cycles_per_week'] * days / 7
    elif mode == 'Battery and charging':
        energy = v['battery_wh'] / 1000 * v['charges_per_day'] * days / (v['charging_efficiency_pct'] / 100)
    elif mode == 'Monthly energy':
        energy = v['kwh_per_month']
    else:
        raise ValueError('Unknown energy input type.')
    return energy * device['quantity']

def defaults(kind, mode):
    values = {key: value for key, _, value, _ in MODES[mode]}
    base, first, second = CATALOG[kind]
    if mode == base:
        fields = MODES[mode]
        values[fields[0][0]] = float(first)
        if second is not None:
            values[fields[1][0]] = float(second)
    if mode == 'Energy per 100 cycles' and base == 'Energy per cycle':
        values.update(kwh_per_100_cycles=float(first * 100), cycles_per_week=float(second))
    return values

def validate(household, devices):
    errors = []
    for key in ('rooms_including_living_room_and_kitchen', 'residents'):
        v = household.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            errors.append(f'{key} must be a positive integer.')
    hours = household.get('hours_at_home_per_day')
    if not isinstance(hours, (int, float)) or not math.isfinite(hours) or not 0 <= hours <= 24:
        errors.append('Hours at home must be between 0 and 24.')
    bill = household.get('past_bill_monthly_kwh')
    if bill is not None and (not isinstance(bill, (int, float)) or not math.isfinite(bill) or bill < 0):
        errors.append('Past bill consumption must be non-negative.')
    days = household.get('month_days', 30)
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 31:
        errors.append('Month length must be between 1 and 31 days.')
    if not devices:
        errors.append('Add at least one appliance before exporting.')
    for d in devices:
        name = d['name'].strip()
        if not name:
            errors.append('Each appliance needs a name.')
        if not isinstance(d['quantity'], int) or d['quantity'] < 1:
            errors.append(f'{name}: quantity must be a positive integer.')
        for key, label, _, maximum in MODES[d['input_mode']]:
            v = d['inputs'][key]['value']
            if not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 or (maximum is not None and v > maximum) or (key == 'charging_efficiency_pct' and v == 0):
                errors.append(f'{name}: invalid {label.lower()}.')
    return errors

def payload(household, devices, assumptions):
    errors = validate(household, devices)
    if errors:
        raise ValueError('\n'.join(errors))
    days = household.get('month_days', 30)
    results = [{'id': d.get('id'), 'monthly_kwh': monthly_energy(d, days)} for d in devices]
    return {'schema_version': '1.1', 'household': household, 'devices': devices,
            'energy_estimate': {'month_days': days, 'total_kwh': sum(r['monthly_kwh'] for r in results), 'devices': results},
            'reference_assumptions': assumptions,
            'reference_profiles': PROFILES,
            'notes': ['All appliance inputs are per unit; quantity applies to identical devices.',
                      'Reference defaults are illustrative editable assumptions, not certified measurements.',
                      'Estimated consumption based on your inputs and reference assumptions. Actual consumption may vary.',
                      'No automatic dwelling multiplier or Gemini integration. Annual energy is prorated using 365 days; weekly cycles use days/7; monthly input covers the selected period.']}
