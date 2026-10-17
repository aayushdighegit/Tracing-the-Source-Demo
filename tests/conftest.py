import pytest


@pytest.fixture(autouse=True)
def _isolated_runtime_files(monkeypatch, tmp_path):
    """Tests never touch the real live-report or sign-in session files."""
    monkeypatch.setenv("LIVE_REPORTS_FILE", str(tmp_path / "live_reports.csv"))
    monkeypatch.setenv("AUTH_SESSIONS_FILE", str(tmp_path / "sessions.json"))
