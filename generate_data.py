import pandas as pd
import random

# 1. BATCHES
batches = ['Contaminated_Buckwheat_7', 'Safe_Rice_A', 'Safe_Flour_B', 'Popular_Bottled_Water']
pd.DataFrame({'batch_id': batches}).to_csv('synthetic_batches.csv', index=False)

# 2. VENDORS & GEOGRAPHY (Targeted: Thane, Dombivli, Kalyan)
# Define exact GPS coordinate boxes for the three local regions
regions = [
    (19.18, 19.24, 72.95, 73.01), # Thane region
    (19.20, 19.23, 73.07, 73.10), # Dombivli region
    (19.23, 19.26, 73.12, 73.16)  # Kalyan region
]

ward_coords = {}
for i in range(1, 25):
    # Randomly assign each ward to one of the three specific areas
    lat_min, lat_max, lon_min, lon_max = random.choice(regions)
    ward_coords[f"Ward_{i}"] = (random.uniform(lat_min, lat_max), random.uniform(lon_min, lon_max))

main_foods = ['Contaminated_Buckwheat_7'] * 25 + ['Safe_Rice_A'] * 25 + ['Safe_Flour_B'] * 25
random.shuffle(main_foods)

vendors = []
for i in range(1, 76):
    ward = f"Ward_{random.randint(1, 24)}"
    lat, lon = ward_coords[ward]
    
    vendors.append({'vendor_id': f'Vendor_{i}', 'ward': ward, 'lat': lat, 'lon': lon, 'batch_received': 'Popular_Bottled_Water'})
    vendors.append({'vendor_id': f'Vendor_{i}', 'ward': ward, 'lat': lat, 'lon': lon, 'batch_received': main_foods[i-1]})
    
df_vendors = pd.DataFrame(vendors)
df_vendors.to_csv('synthetic_vendors.csv', index=False)

# 3. PATIENTS
patients = []
for i in range(1, 301):
    vendor_id = f"Vendor_{random.randint(1, 75)}"
    vendor_row = df_vendors[(df_vendors['vendor_id'] == vendor_id) & (df_vendors['batch_received'] != 'Popular_Bottled_Water')]
    primary_batch = vendor_row['batch_received'].iloc[0]

    if primary_batch == 'Contaminated_Buckwheat_7':
        status = random.choices(['Sick', 'Healthy'], weights=[0.80, 0.20])[0]
        report_day = random.choices([1, 2, 3], weights=[0.1, 0.4, 0.5])[0] if status == 'Sick' else random.choice([1, 2, 3])
    else:
        status = random.choices(['Sick', 'Healthy'], weights=[0.05, 0.95])[0]
        report_day = random.choice([1, 2, 3])

    if random.random() < 0.10:
        vendor_id = f"Vendor_{random.randint(1, 75)}"

    patients.append({
        'patient_id': f'Patient_{i}',
        'reported_vendor': vendor_id,
        'status': status,
        'report_day': report_day
    })

pd.DataFrame(patients).to_csv('synthetic_patients.csv', index=False)
print("Successfully generated coordinates for Thane, Dombivli, and Kalyan!")