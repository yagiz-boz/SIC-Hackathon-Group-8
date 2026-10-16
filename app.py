import json
from uuid import uuid4
import streamlit as st
from core import CATALOG, MODES, PROFILES, recommended_modes, monthly_energy, defaults, payload, validate

st.set_page_config(page_title='EcoWatt AI', page_icon='🌱', layout='wide')
st.title('🌱 EcoWatt AI')
st.write('Understand your home, one appliance at a time.')
st.caption('Local energy estimates • No Gemini connection')
st.session_state.setdefault('devices', [])
house_tab, ref_tab, device_tab, summary_tab, energy_tab = st.tabs(['1 · Household', '2 · Reference assumptions', '3 · Appliances', '4 · Summary & export', '5 · Energy Consumption'])

with house_tab:
    st.header('Your household')
    a, b = st.columns(2)
    dwelling = a.selectbox('Home type', ['Apartment', 'Detached house / Villa', 'Other'], key='dwelling')
    days = b.number_input('Days in the month / billing period', min_value=1, max_value=31, value=30, step=1, key='month_days')
    if dwelling == 'Detached house / Villa':
        st.info('Remember outdoor lighting, pumps, electric water heating and other equipment. Add these as custom devices. Home type alone does not increase the estimate.')
    rooms = a.number_input('Room count (including living room and kitchen)', min_value=1, value=3, step=1, key='rooms')
    residents = b.number_input('Number of residents', min_value=1, value=2, step=1, key='residents')
    hours = a.number_input('Hours at home per day', min_value=0.0, max_value=24.0, value=14.0, step=0.5, key='home_hours', help='Typical hours the household is occupied; appliance use is entered separately.')
    known_bill = b.checkbox('I know my past monthly electricity consumption', key='known_bill')
    bill = b.number_input('Past bill consumption (kWh/month)', min_value=0.0, value=200.0, step=1.0, key='bill', disabled=not known_bill)
    st.caption('The bill is optional. Enter energy in kWh, not the amount paid. An unknown bill is exported as null.')
household = dict(home_type=dwelling, month_days=days, rooms_including_living_room_and_kitchen=rooms, residents=residents, hours_at_home_per_day=hours, past_bill_monthly_kwh=bill if known_bill else None)

with ref_tab:
    st.header('Editable reference assumptions')
    st.warning('These are illustrative starting values, not verified product data. Actual consumption varies with model, settings, climate and use.')
    st.write('Unknown fields use these values and stay marked as estimates. Changes apply immediately to all fields using a reference.')
    ref_kind = st.selectbox('Appliance reference to edit', list(CATALOG), key='ref_kind')
    st.caption('Power means average operating electrical input, not heating/cooling output or a maximum nameplate rating. One oven cycle means one cooking session; one lighting unit means one bulb.')

# Render every reference widget so Streamlit preserves edits when switching type.
assumptions = {}
for kind in CATALOG:
    assumptions[kind] = {}
    with ref_tab:
        with st.expander(f'{kind} assumptions', expanded=kind == ref_kind):
            st.caption(f'Representative profile: {PROFILES[kind]}. Editable project estimate, not a measured or market-average value.')
            for mode, fields in MODES.items():
                with st.expander(mode):
                    assumptions[kind][mode] = {}
                    for key, label, _, maximum in fields:
                        val = st.number_input(label, min_value=0.1 if key == 'charging_efficiency_pct' else 0.0, max_value=maximum, value=defaults(kind, mode)[key], step=0.1, key=f'ref:{kind}:{mode}:{key}')
                        assumptions[kind][mode][key] = val

with device_tab:
    st.header('Your appliances')
    st.write('Add a group for identical appliances. Add separate groups when their power or usage differs. All values below are per appliance.')
    kind = st.selectbox('Appliance type to add', list(CATALOG), key='add_kind')
    if st.button('Add appliance', type='primary'):
        st.session_state.devices.append({'id': uuid4().hex, 'type': kind})
        st.rerun()
    if not st.session_state.devices:
        st.info('Choose a type and select Add appliance. You can leave technical values unknown.')

devices = []
type_counts = {}
for item in list(st.session_state.devices):
    uid, kind = item['id'], item['type']
    type_counts[kind] = type_counts.get(kind, 0) + 1
    display_name = st.session_state.get(f'{uid}:name', kind).strip() or kind
    same_type_groups = sum(d['type'] == kind for d in st.session_state.devices)
    heading = f'{display_name} · Group {type_counts[kind]}' if same_type_groups > 1 else display_name
    with device_tab:
        with st.expander(heading, expanded=True):
            name = st.text_input('Appliance name', value=kind, key=f'{uid}:name', max_chars=120)
            quantity = st.number_input('Quantity', min_value=1, value=1, step=1, key=f'{uid}:quantity')
            with st.expander('Advanced options'):
                advanced = st.checkbox('Show all energy input types', key=f'{uid}:advanced')
                st.caption('Alternative modes use generic starting assumptions. Review them before calculating.')
            options = list(MODES) if advanced or kind == 'Custom device' else recommended_modes(kind)
            if st.session_state.get(f'{uid}:mode', options[0]) not in options:
                st.session_state[f'{uid}:mode'] = options[0]
            mode = st.selectbox('Energy input type', options, index=options.index(CATALOG[kind][0]), key=f'{uid}:mode')
            if kind == 'Phone':
                st.caption('Use Wh (not mAh). Charges are full-equivalent charges; two half charges equal one. Charging efficiency accounts for wall-to-battery losses.')
            if kind in ('Air conditioner', 'Electric heater', 'Refrigerator'):
                st.caption('Power-based usage must reflect operating time and cycling. Annual or monthly label energy can be more representative.')
            inputs = {}
            for key, label, _, maximum in MODES[mode]:
                known = st.checkbox(f'I know: {label}', key=f'{uid}:{mode}:{key}:known')
                reference = assumptions[kind][mode][key]
                if known:
                    value = st.number_input(label, min_value=0.1 if key == 'charging_efficiency_pct' else 0.0, max_value=maximum, value=reference, step=0.1, key=f'{uid}:{mode}:{key}:value')
                else:
                    value = reference
                    st.caption(f'Using estimated reference: {value:g} — {label}')
                inputs[key] = {'value': value, 'source': 'user_provided' if known else 'reference_estimate', 'reference_key': f'{kind}/{mode}/{key}' if not known else None}
            estimated = any(v['source'] == 'reference_estimate' for v in inputs.values())
            st.info('Estimated inputs are in use.' if estimated else 'All inputs are user-provided; they have not been independently verified.')
            if st.button('Remove appliance', key=f'{uid}:remove'):
                st.session_state.devices = [d for d in st.session_state.devices if d['id'] != uid]
                st.rerun()
            devices.append(dict(id=uid, type=kind, name=name.strip(), quantity=quantity, input_mode=mode, inputs=inputs, contains_estimates=estimated))

with summary_tab:
    st.header('Collected data')
    st.json(household)
    st.metric('Appliances (including quantities)', sum(d['quantity'] for d in devices))
    rows = []
    for d in devices:
        for key, value in d['inputs'].items():
            label = next(f[1] for f in MODES[d['input_mode']] if f[0] == key)
            rows.append({'Appliance': d['name'], 'Type': d['type'], 'Quantity': d['quantity'], 'Input': label, 'Value per unit': f"{value['value']:g}", 'Source': 'Estimated reference' if value['source'] == 'reference_estimate' else 'User provided'})
    if rows:
        st.dataframe(rows, hide_index=True, width='stretch')
    errors = validate(household, devices)
    if errors:
        for error in errors:
            st.error(error)
    else:
        data = payload(household, devices, assumptions)
        st.success('Data and monthly energy estimates are ready to export.')
        st.download_button('Download collected data (JSON)', json.dumps(data, indent=2, allow_nan=False), file_name='ecowatt_household.json', mime='application/json')
        with st.expander('Preview full structured data'):
            st.json(data)
    st.caption('Only the downloaded JSON persists. Refreshing or closing your session may clear entries. No data is sent to Gemini or another analysis service.')

with energy_tab:
    st.header('Energy Consumption')
    st.write('Estimated consumption based on your inputs and reference assumptions. Actual consumption may vary.')
    st.caption(f'Based on {days} days and the appliances you added. This is an appliance inventory estimate, not a meter reading.')
    if errors:
        st.info('Complete the valid household and appliance inputs to calculate consumption.')
    else:
        energy_rows = [{'Appliance': d['name'], 'Quantity': d['quantity'], 'Monthly energy (kWh)': monthly_energy(d, days), 'Input source': 'Includes estimated references' if d['contains_estimates'] else 'User provided'} for d in devices]
        total = sum(r['Monthly energy (kWh)'] for r in energy_rows)
        st.metric('Estimated total electricity consumption', f'{total:,.1f} kWh/month')
        st.dataframe(energy_rows, hide_index=True, width='stretch', column_config={'Monthly energy (kWh)': st.column_config.NumberColumn(format='%.1f')})
        st.bar_chart([{'Appliance': r['Appliance'] + f' ({i+1})', 'kWh': r['Monthly energy (kWh)']} for i, r in enumerate(energy_rows)], x='Appliance', y='kWh')
        if known_bill:
            st.metric('Past bill consumption', f'{bill:,.1f} kWh')
            st.write(f'Difference from past bill: {total - bill:+,.1f} kWh. Compare only matching periods and similar usage.')
        with st.expander('How this estimate is calculated'):
            st.write('Power: W ÷ 1,000 × hours/day × days. Annual energy: kWh/year × days ÷ 365. Cycle energy: kWh/cycle × cycles/week × days ÷ 7. Values per 100 cycles are divided by 100 first. Phone: Wh ÷ 1,000 × charges/day × days ÷ charging efficiency. Monthly input is used as entered for this period. Each result is multiplied by quantity once.')
            st.caption('No automatic multiplier for rooms, residents or home type. No extra standby energy is added. Seasonal devices reflect the daily use you enter; refrigerator annual energy is distributed evenly across the year.')
