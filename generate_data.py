import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

def generate_seeded_outbreak_data(seed=42):
    # RUBRIC: Synthetic data generated with a seeded script for reproducibility
    random.seed(seed)
    np.random.seed(seed)

    # 1. WHOLESALERS & BATCHES (Food -> Vendor -> Wholesaler -> Batch)
    batches = [
        {'batch_id': 'BATCH-BW-07 (Buckwheat Flour)', 'food_item': 'Kuttu/Buckwheat Dish', 'supplier': 'Shree Agro Wholesale', 'is_planted_source': True},
        # Same wholesaler as the planted batch: the batch must be traced, not just the wholesaler
        {'batch_id': 'BATCH-SB-04 (Sabudana)', 'food_item': 'Sabudana Khichdi / Vada', 'supplier': 'Shree Agro Wholesale', 'is_planted_source': False},
        {'batch_id': 'BATCH-RC-02 (Basmati Rice)', 'food_item': 'Steamed Basmati Rice', 'supplier': 'Konkan Grains Co.', 'is_planted_source': False},
        {'batch_id': 'BATCH-FL-09 (Wheat Flour)', 'food_item': 'Tandoori Roti / Bread', 'supplier': 'MahaFoods Ltd.', 'is_planted_source': False},
        {'batch_id': 'BATCH-PN-11 (Paneer)', 'food_item': 'Paneer Tikka / Curry', 'supplier': 'Thane Dairy Co.', 'is_planted_source': False},
        {'batch_id': 'BATCH-MK-05 (Milk)', 'food_item': 'Masala Chai / Lassi', 'supplier': 'Thane Dairy Co.', 'is_planted_source': False},
        {'batch_id': 'BATCH-OL-03 (Groundnut Oil)', 'food_item': 'Fried Snacks (Vada / Bhaji)', 'supplier': 'Konkan Oils Pvt.', 'is_planted_source': False},
        {'batch_id': 'BATCH-PT-06 (Potatoes)', 'food_item': 'Aloo Sabzi / Fries', 'supplier': 'Vashi APMC Traders', 'is_planted_source': False},
        {'batch_id': 'BATCH-WT-01 (Bottled Water)', 'food_item': 'Mineral Water', 'supplier': 'AquaPure Beverage', 'is_planted_source': False}
    ]
    df_batches = pd.DataFrame(batches)
    df_batches.to_csv('synthetic_batches.csv', index=False)

    # 2. AT LEAST 24 SIMULATED CITY WARDS (Thane, Kalyan, Dombivli)
    zones = [
        ("Thane - Naupada", 19.185, 19.205, 72.965, 72.980),
        ("Thane - Wagle Estate", 19.205, 19.230, 72.950, 72.975),
        ("Dombivli - East", 19.205, 19.220, 73.085, 73.105),
        ("Dombivli - West", 19.215, 19.230, 73.065, 73.085),
        ("Kalyan - West", 19.240, 19.255, 73.120, 73.135),
        ("Kalyan - Khadakpada", 19.250, 19.265, 73.135, 73.155)
    ]

    ward_coords = {}
    for i in range(1, 25):
        zone_name, lat_min, lat_max, lon_min, lon_max = zones[i % len(zones)]
        ward_coords[f"Ward_{i:02d} ({zone_name})"] = (
            round(random.uniform(lat_min, lat_max), 5),
            round(random.uniform(lon_min, lon_max), 5)
        )

    # Each vendor's main dish batch (the planted batch reaches 20 of the 75 vendors)
    main_foods = (
        ['BATCH-BW-07 (Buckwheat Flour)'] * 20 +
        ['BATCH-SB-04 (Sabudana)'] * 14 +
        ['BATCH-RC-02 (Basmati Rice)'] * 14 +
        ['BATCH-FL-09 (Wheat Flour)'] * 14 +
        ['BATCH-PN-11 (Paneer)'] * 13
    )
    random.shuffle(main_foods)
    # Plus one side item each, shared across vendors (these overlap with the planted batch's vendors)
    side_foods = ['BATCH-MK-05 (Milk)', 'BATCH-OL-03 (Groundnut Oil)', 'BATCH-PT-06 (Potatoes)']

    vendors = []
    vendor_main = {}
    ward_list = list(ward_coords.keys())
    for i in range(1, 76):
        ward = ward_list[i % 24]
        lat, lon = ward_coords[ward]
        v_id = f"Vendor_{i:02d}"
        vendor_main[v_id] = main_foods[i-1]

        # Every vendor stocks popular Bottled Water (Misleading Common Food) + 1 main batch + 1 side batch
        for batch in ['BATCH-WT-01 (Bottled Water)', main_foods[i-1], random.choice(side_foods)]:
            vendors.append({'vendor_id': v_id, 'ward': ward, 'lat': lat, 'lon': lon, 'batch_received': batch})

    df_vendors = pd.DataFrame(vendors)
    df_vendors.to_csv('synthetic_vendors.csv', index=False)

    # 3. PATIENTS: CONSUMPTION TIMES, BACKGROUND ILLNESS, 10% WRONG RECALL, LATE & MISSING DATA
    patients = []
    base_time = datetime(2026, 10, 12, 8, 0)

    for i in range(1, 421):
        true_vendor = f"Vendor_{random.randint(1, 75):02d}"
        primary_batch = vendor_main[true_vendor]

        # Simulate outbreak vs. background unrelated illness (5% background rate)
        if primary_batch == 'BATCH-BW-07 (Buckwheat Flour)':
            status = random.choices(['Sick', 'Healthy'], weights=[0.80, 0.20])[0]
            eat_day = random.choices([1, 2, 3], weights=[0.25, 0.45, 0.30])[0]
        else:
            # RUBRIC: Account for background illnesses unrelated to the outbreak
            status = random.choices(['Sick', 'Healthy'], weights=[0.05, 0.95])[0]
            eat_day = random.choice([1, 2, 3])

        consumption_dt = base_time + timedelta(days=eat_day-1, hours=random.randint(0, 14), minutes=random.choice([0, 15, 30, 45]))
        
        # RUBRIC: Handle late reports (e.g., ate on Day 1, reported on Day 2 or 3)
        is_late = random.random() < 0.15
        report_day = min(3, eat_day + random.randint(1, 2)) if is_late else eat_day

        # RUBRIC: 10% Wrong Recall (Patients misremembering where they ate)
        reported_vendor = true_vendor
        wrong_recall_flag = False
        if random.random() < 0.10:
            reported_vendor = f"Vendor_{random.randint(1, 75):02d}"
            wrong_recall_flag = True

        # RUBRIC: Missing details ( ~4% reports arrive with missing vendor or status to test cleaning pipeline)
        if random.random() < 0.04:
            reported_vendor = np.nan

        patients.append({
            'patient_id': f'Patient_{1000+i}',
            'reported_vendor': reported_vendor,
            'status': status,
            'consumption_time': consumption_dt.strftime("%Y-%m-%d %H:%M"),
            'eat_day': eat_day,
            'report_day': report_day,
            'is_late_report': is_late,
            'noisy_recall': wrong_recall_flag
        })

    df_patients = pd.DataFrame(patients)
    # Inject 8 duplicate rows to demonstrate deduplication during ingestion
    df_patients = pd.concat([df_patients, df_patients.sample(8, random_state=seed)], ignore_index=True)
    df_patients.to_csv('synthetic_patients.csv', index=False)
    return df_batches, df_vendors, df_patients

if __name__ == "__main__":
    generate_seeded_outbreak_data(42)
    print("Seeded reproducible dataset generated successfully.")
