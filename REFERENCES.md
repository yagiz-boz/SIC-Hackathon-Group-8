# Reference profiles

These defaults describe familiar household device categories, not a verified ranking of best-selling models or measured national averages. Numerical values are rounded, editable project assumptions unless explicitly stated below. Device age, size and usage can change energy substantially. Unknown fields retain reference provenance in JSON. Usage hours and weekly cycles are separate behavioral assumptions, not product facts.

| Profile | Default per unit | Usage assumption |
|---|---|---|
| Medium-size LED TV | 80 W | 4 h/day |
| Everyday laptop | 50 W | 5 h/day |
| Everyday desktop and monitor | 200 W | 5 h/day |
| Modern medium-size fridge-freezer | 250 kWh/year | Annual input |
| Console during gameplay | 150 W | 2 h/day |
| Single-room split AC | 1,000 W average electrical input | 4 equivalent operating h/day |
| Portable resistance heater | 1,500 W | 3 equivalent operating h/day |
| Electric oven | 1 kWh/cooking session | 3 sessions/week |
| Standard household washer | 0.6 kWh/wash | 4 washes/week |
| Standard household dishwasher | 0.8 kWh/wash | 5 washes/week |
| Smartphone | 15.4 Wh; 85% charging efficiency | 1 full-equivalent charge/day |
| One LED bulb | 9 W | 5 h/day |
| Custom device | Generic 100 W | 3 h/day; review this placeholder |

Phone battery energy is an illustrative conversion of 4 Ah × 3.85 V, not a claim about every phone. Charging efficiency is a project assumption. Manufacturer maximum/adapter ratings can exceed average operating power. Non-recommended modes have generic placeholders and need review; switching modes does not convert existing input values.

## Background sources checked 2026-10-16

- [Virginia Cooperative Extension / Virginia Tech, Estimating Appliance and Home Electronic Energy Use](https://ext.vt.edu/content/pubs_ext_vt_edu/en/2901/2901-9014/2901-9014.html): supports the power/time calculation, cautions about cycling appliances and lists illustrative power ratings, including a 50 W laptop and portable heaters up to 1,500 W. Its older TV/refrigerator examples are not used as modern product averages.
- [European Commission: EPREL](https://energy-efficient-products.ec.europa.eu/eprel_en): source for model-specific energy labels when available. No live EPREL lookup, sampled model median or certified-product claim is implemented here.
- [ENERGY STAR: dishwashers](https://www.energystar.gov/products/dishwashers): explains comparing model-specific label consumption. It does not establish the 0.8 kWh project assumption above.

The application does not ask users to choose a wash programme. Cycle reference values still depend on operating conditions; they are estimates and may differ from actual washes. Replace a reference with a matching label value or measurement whenever known.
