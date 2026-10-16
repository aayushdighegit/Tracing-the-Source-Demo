"""Checks that the source ranking only uses past data and finds the planted source early.

The ranking function is loaded straight from app.py (without running the Streamlit UI),
so these tests exercise the exact code the dashboard uses.
"""
import ast
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_engine():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_bayesian_traceback")
    namespace = {"pd": pd, "nx": nx}
    exec(compile(ast.Module(body=[func], type_ignores=[]), "app.py", "exec"), namespace)
    return namespace["run_bayesian_traceback"]


run_bayesian_traceback = _load_engine()


@pytest.fixture(scope="module")
def data():
    batches = pd.read_csv(ROOT / "synthetic_batches.csv")
    vendors = pd.read_csv(ROOT / "synthetic_vendors.csv")
    raw = pd.read_csv(ROOT / "synthetic_patients.csv")
    # Same cleaning as the dashboard: deduplicate, then drop reports missing vendor or status
    cleaned = raw.drop_duplicates(subset=["patient_id"]).dropna(subset=["reported_vendor", "status"]).copy()
    planted = batches.loc[batches["is_planted_source"], "batch_id"].iloc[0]
    return batches, vendors, cleaned, planted


@pytest.mark.parametrize("day", [1, 2, 3])
def test_only_reports_up_to_selected_day_are_used(data, day):
    batches, vendors, cleaned, _ = data
    available, sick, _, _, _ = run_bayesian_traceback(cleaned, vendors, batches, day)
    assert available["report_day"].max() <= day
    assert len(available) == (cleaned["report_day"] <= day).sum()
    assert set(sick["patient_id"]) <= set(available["patient_id"])


@pytest.mark.parametrize("day", [1, 2])
def test_future_reports_cannot_change_past_rankings(data, day):
    batches, vendors, cleaned, _ = data
    _, _, _, with_future, _ = run_bayesian_traceback(cleaned, vendors, batches, day)

    # Flip every future report to "Sick" at the most popular food: if any future data leaked in,
    # the past ranking would change.
    poisoned = cleaned.copy()
    future = poisoned["report_day"] > day
    poisoned.loc[future, "status"] = "Sick"
    poisoned.loc[future, "reported_vendor"] = "Vendor_01"
    _, _, _, poisoned_scores, _ = run_bayesian_traceback(poisoned, vendors, batches, day)

    pd.testing.assert_frame_equal(with_future, poisoned_scores)


@pytest.mark.parametrize("day", [1, 2, 3])
def test_planted_source_is_ranked_first_every_day(data, day):
    batches, vendors, cleaned, planted = data
    _, _, _, scores, _ = run_bayesian_traceback(cleaned, vendors, batches, day)
    assert scores.iloc[0]["Batch"] == planted
    assert planted in scores.head(3)["Batch"].tolist()


def test_beats_raw_case_count_baseline(data):
    batches, vendors, cleaned, planted = data
    _, sick, _, scores, _ = run_bayesian_traceback(cleaned, vendors, batches, 3)
    baseline = sick.merge(vendors, left_on="reported_vendor", right_on="vendor_id")["batch_received"].value_counts()
    # The baseline is fooled by the misleading common food (bottled water); the Bayesian ranking is not
    assert baseline.index[0] != planted
    assert scores.iloc[0]["Batch"] == planted


def test_dataset_meets_problem_statement_scale(data):
    batches, vendors, _, _ = data
    assert vendors["ward"].nunique() >= 24
    assert batches["supplier"].nunique() >= 2
    assert batches["is_planted_source"].sum() == 1
