import pandas as pd
import random

# 1. REALISTIC BATCH IDs (No "Contaminated" label cheating)
batches = [
    {'batch_id': 'LOT-BW-407 (Buckwheat Flour)', 'supplier': 'Shree Agro Mills'},
    {'batch_id': 'LOT-RC-102 (Basmati Rice)', 'supplier': 'Konkan Grains Co.'},
    {'batch_id': 'LOT-FL-889 (Wheat Flour)', 'supplier': 'MahaFoods Ltd.'},
    {'batch_id': 'LOT-WT-001 (Bottled Water)', 'supplier': 'AquaPure Beverage'}
]
pd.DataFrame(batches).to_csv('synthetic_batches.csv', index=False)

# 2. REAL LOCAL ZONES (Thane, Dombivli, Kalyan)
zones = [
    ("Thane - Naupada", 19.185, 19.205, 72.965, 72.980),
    ("Thane - Wagle Estate", 19.205, 19.230, 72.950, 72.975),
    ("Dombivli - East MIDC", 19.205, 19.220, 73.085, 73.105),
    ("Dombivli - West", 19.215, 19.230, 73.065, 73.085),
    ("Kalyan - West Station", 19.240, 19.255, 73.120, 73.135),
    ("Kalyan - Khadakpada", 19.250, 19.265, 73.135, 73.155)
]

ward_coords = {}
for i in range(1, 25):
    zone_name, lat_min, lat_max, lon_min, lon_max = random.choice(zones)
    ward_coords[f"Ward_{i:02d} ({zone_name})"] = (
        random.uniform(lat_min, lat_max),
        random.uniform(lon_min, lon_max)
    )

main_foods = (
    ['LOT-BW-407 (Buckwheat Flour)'] * 25 +
    ['LOT-RC-102 (Basmati Rice)'] * 25 +
    ['LOT-FL-889 (Wheat Flour)'] * 25
)
random.shuffle(main_foods)

vendors = []
ward_list = list(ward_coords.keys())
for i in range(1, 76):
    ward = random.choice(ward_list)
    lat, lon = ward_coords[ward]
    v_id = f"Vendor_{i:02d}"
    
    # Every vendor stocks bottled water (The Baseline Trap) + 1 primary ingredient
    vendors.append({'vendor_id': v_id, 'ward': ward, 'lat': lat, 'lon': lon, 'batch_received': 'LOT-WT-001 (Bottled Water)'})
    vendors.append({'vendor_id': v_id, 'ward': ward, 'lat': lat, 'lon': lon, 'batch_received': main_foods[i-1]})

df_vendors = pd.DataFrame(vendors)
df_vendors.to_csv('synthetic_vendors.csv', index=False)

# 3. PATIENTS WITH REALISTIC SYMPTOM LOGS
patients = []
for i in range(1, 351):
    vendor_id = f"Vendor_{random.randint(1, 75):02d}"
    vendor_row = df_vendors[(df_vendors['vendor_id'] == vendor_id) & (df_vendors['batch_received'] != 'LOT-WT-001 (Bottled Water)')]
    primary_batch = vendor_row['batch_received'].iloc[0]

    if primary_batch == 'LOT-BW-407 (Buckwheat Flour)':
        status = random.choices(['Sick', 'Healthy'], weights=[0.82, 0.18])[0]
        report_day = random.choices([1, 2, 3], weights=[0.15, 0.35, 0.50])[0] if status == 'Sick' else random.choice([1, 2, 3])
    else:
        status = random.choices(['Sick', 'Healthy'], weights=[0.05, 0.95])[0]
        report_day = random.choice([1, 2, 3])

    # 12% faulty patient recall noise
    if random.random() < 0.12:
        vendor_id = f"Vendor_{random.randint(1, 75):02d}"

    patients.append({
        'patient_id': f'PT-{1000+i}',
        'reported_vendor': vendor_id,
        'status': status,
        'report_day': report_day
    })

pd.DataFrame(patients).to_csv('synthetic_patients.csv', index=False)
print("Generated realistic dataset without hardcoded labels.")
