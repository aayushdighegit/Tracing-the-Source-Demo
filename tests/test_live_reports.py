"""Live case reports: saved to the dataset, picked up by every view, and resettable."""
from datetime import time as clock_time
from pathlib import Path

import pytest

import live_reports as lr

ROOT = Path(__file__).resolve().parents[1]


def test_report_fields_and_late_flag():
    r = lr.build_report("Patient_1500", "Vendor_10", "Sick", 1, clock_time(13, 30), 3)
    assert r["consumption_time"] == "2026-10-12 13:30" and r["is_late_report"] is True
    on_time = lr.build_report("Patient_1501", "Vendor_10", "Healthy", 3, clock_time(9, 0), 3)
    assert on_time["is_late_report"] is False and on_time["consumption_time"] == "2026-10-14 09:00"
    with pytest.raises(ValueError):
        lr.build_report("Patient_1502", "Vendor_10", "Sick", 3, clock_time(9, 0), 2)   # can't report before eating


def test_append_load_clear_and_ids():
    assert lr.load_live().empty
    lr.append_live(lr.build_report("Patient_1421", "Vendor_02", "Sick", 2, clock_time(12, 0), 2))
    df = lr.load_live()
    assert list(df["patient_id"]) == ["Patient_1421"] and bool(df["is_late_report"].iloc[0]) is False
    assert lr.next_patient_id(["Patient_1001", "Patient_1420", "Patient_1421"]) == "Patient_1422"
    lr.clear_live()
    assert lr.load_live().empty


def _open_app():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.secrets["MINIMOTH_API_KEY"] = ""          # open demo mode, regardless of local secrets
    return at


def _cleaned_count(at):
    import re
    md = " ".join(m.value for m in at.markdown)
    return int(re.search(r"of (\d+) cleaned reports", md).group(1))


def test_submitted_report_changes_the_data_and_survives_a_refresh():
    at = _open_app()
    at.run()
    before = _cleaned_count(at)

    at.sidebar.selectbox[0].set_value("Vendor_10")
    at.sidebar.radio[0].set_value("Sick")
    at.sidebar.button[0].click().run()                 # Submit case report
    assert not at.exception
    assert _cleaned_count(at) == before + 1

    refreshed = _open_app()                            # a brand-new session = a page refresh
    refreshed.run()
    assert _cleaned_count(refreshed) == before + 1
    assert len(lr.load_live()) == 1

    reset = next(b for b in refreshed.button if b.label == "Reset to original data")
    reset.click().run()
    assert _cleaned_count(refreshed) == before and lr.load_live().empty


def test_hotspot_rankings_are_shown():
    at = _open_app()
    at.run()
    md = " ".join(m.value for m in at.markdown)
    assert "Ward ranking" in md and "Vendor ranking" in md and 'class="wrap-table hotspot"' in md
