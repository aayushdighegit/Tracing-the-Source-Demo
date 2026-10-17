"""Live case reports submitted from the dashboard.

Reports are saved to their own CSV (live_reports.csv, git-ignored) and merged with the
seeded dataset on every run, so they change the data everyone sees and survive page
reloads and restarts, while the seeded files stay untouched and reproducible.
"""
import os
import re
import threading
from datetime import datetime, timedelta

import pandas as pd

COLUMNS = ['patient_id', 'reported_vendor', 'status', 'consumption_time', 'eat_day',
           'report_day', 'is_late_report', 'noisy_recall']
OUTBREAK_START = datetime(2026, 10, 12)   # Day 1 of the simulated outbreak (matches generate_data.py)
MAX_LIVE_REPORTS = 500                    # keeps a public demo from growing without limit

_lock = threading.Lock()


def live_file():
    return os.environ.get("LIVE_REPORTS_FILE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_reports.csv")


def load_live():
    path = live_file()
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLUMNS)
    try:
        df = pd.read_csv(path)
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=COLUMNS)
    for col in ('is_late_report', 'noisy_recall'):
        df[col] = df[col].astype(str).str.lower().eq('true')
    return df[COLUMNS]


def next_patient_id(existing_ids):
    nums = [int(m.group(1)) for m in (re.match(r"Patient_(\d+)$", str(i)) for i in existing_ids) if m]
    return f"Patient_{(max(nums) if nums else 1000) + 1}"


def build_report(patient_id, vendor, status, eat_day, eat_time, report_day):
    """One report row. Late = reported on a later day than the food was eaten."""
    eat_day, report_day = int(eat_day), int(report_day)
    if not 1 <= eat_day <= report_day:
        raise ValueError("The day eaten must be between Day 1 and the report day.")
    when = OUTBREAK_START + timedelta(days=eat_day - 1, hours=eat_time.hour, minutes=eat_time.minute)
    return {
        'patient_id': patient_id, 'reported_vendor': vendor, 'status': status,
        'consumption_time': when.strftime("%Y-%m-%d %H:%M"), 'eat_day': eat_day,
        'report_day': report_day, 'is_late_report': eat_day < report_day, 'noisy_recall': False,
    }


def append_live(report):
    with _lock:
        df = load_live()
        if len(df) >= MAX_LIVE_REPORTS:
            raise RuntimeError(f"The live report limit ({MAX_LIVE_REPORTS}) is reached. Reset live reports to continue.")
        df = pd.concat([df, pd.DataFrame([report])[COLUMNS]], ignore_index=True)
        path = live_file()
        tmp = path + ".tmp"
        df.to_csv(tmp, index=False)
        os.replace(tmp, path)


def clear_live():
    with _lock:
        try:
            os.remove(live_file())
        except FileNotFoundError:
            pass
