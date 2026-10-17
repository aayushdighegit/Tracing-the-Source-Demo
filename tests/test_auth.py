"""Tests for the MiniMoth phone-OTP sign-in. No network: MiniMoth is replaced by a fake."""
import io
import json
import time
import urllib.error
from pathlib import Path

import pytest

import auth
from auth import (MiniMothClient, MiniMothError, SessionStore, ensure_fresh, end_session,
                  mask_phone, normalize_phone, parse_allowlist)

ROOT = Path(__file__).resolve().parents[1]
OFFICER = "+919876543210"
STRANGER = "+919000000001"


# ---------- helpers ----------

def test_normalize_phone_accepts_common_indian_formats():
    for raw in ["+919876543210", "919876543210", "9876543210", "098765 43210", "+91 98765-43210"]:
        assert normalize_phone(raw) == OFFICER
    for bad in ["", "12345", "+915876543210", "+14155550100", None]:
        assert normalize_phone(bad) is None


def test_allowlist_and_masking():
    assert parse_allowlist("+919876543210, 9123456789\n bad") == {OFFICER, "+919123456789"}
    assert parse_allowlist(["9876543210"]) == {OFFICER}
    assert mask_phone(OFFICER) == "+91 •••••• 3210"


# ---------- REST client ----------

class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_client_sends_api_key_and_json():
    seen = {}

    def opener(req, timeout):
        seen.update(url=req.full_url, key=req.get_header("X-api-key"), body=json.loads(req.data))
        assert "Python-urllib" not in (req.get_header("User-agent") or "")   # blocked by MiniMoth's Cloudflare
        return _Resp(b'{"message": "OTP sent", "otp_id": "abc"}')

    out = MiniMothClient("mm_test_k", opener=opener).send_otp(OFFICER)
    assert out["otp_id"] == "abc"
    assert seen == {"url": "https://api.minimoth.dev/v1/otp/send", "key": "mm_test_k", "body": {"phone": OFFICER}}


def test_client_maps_api_errors_to_codes():
    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad", {}, io.BytesIO(b'{"code": "INVALID_OTP", "error": "wrong"}'))

    with pytest.raises(MiniMothError) as e:
        MiniMothClient("mm_test_k", opener=opener).verify_otp(OFFICER, "111111")
    assert e.value.code == "INVALID_OTP" and "Incorrect" in e.value.friendly


def test_client_reports_network_failures():
    def opener(req, timeout):
        raise urllib.error.URLError("offline")

    with pytest.raises(MiniMothError) as e:
        MiniMothClient("mm_test_k", opener=opener).send_otp(OFFICER)
    assert e.value.code == "NETWORK_ERROR"


# ---------- server-side sessions ----------

class FakeMiniMoth:
    """Behaves like the MiniMoth sandbox: the code is always 000000."""

    def __init__(self):
        self.sent, self.valid, self.logged_out, self.n = [], True, [], 0

    def _tokens(self, ttl=300):
        self.n += 1
        exp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + ttl))
        return {"access_token": f"at{self.n}", "refresh_token": f"rt{self.n}", "expires_at": exp}

    def send_otp(self, phone):
        self.sent.append(phone)
        return {"message": "OTP sent", "otp_id": "x"}

    def verify_otp(self, phone, code):
        if code != "000000":
            raise MiniMothError("INVALID_OTP")
        return self._tokens()

    def validate(self, token):
        return {"valid": self.valid}

    def refresh(self, token):
        return self._tokens()

    def logout(self, token):
        self.logged_out.append(token)
        return {}


def test_tokens_stay_server_side_and_refresh_before_expiry():
    mm, store = FakeMiniMoth(), SessionStore()
    handle = store.create(OFFICER, mm.verify_otp(OFFICER, "000000"))
    assert "at1" not in handle and len(handle) >= 40            # the cookie value is an opaque random handle
    store.update(handle, expires_at=time.time() + 5)               # access token about to expire
    s = ensure_fresh(mm, store, handle)
    assert s["access_token"] == "at2" and s["refresh_token"] == "rt2"   # both tokens rotated


def test_revoked_session_is_dropped_on_revalidation():
    mm, store = FakeMiniMoth(), SessionStore()
    handle = store.create(OFFICER, mm.verify_otp(OFFICER, "000000"))
    store.update(handle, last_validated=0)
    mm.valid = False
    assert ensure_fresh(mm, store, handle) is None
    assert store.get(handle) is None


def test_logout_revokes_at_minimoth_and_forgets_locally():
    mm, store = FakeMiniMoth(), SessionStore()
    handle = store.create(OFFICER, mm.verify_otp(OFFICER, "000000"))
    end_session(mm, store, handle)
    assert mm.logged_out == ["at1"] and store.get(handle) is None


def test_sessions_survive_a_server_restart(tmp_path):
    path = str(tmp_path / "sessions.json")
    mm = FakeMiniMoth()
    handle = SessionStore(path).create(OFFICER, mm.verify_otp(OFFICER, "000000"))
    restarted = SessionStore(path)                                 # new process reading the same file
    assert restarted.get(handle)["phone"] == OFFICER
    restarted.delete(handle)
    assert SessionStore(path).get(handle) is None                  # logout is persisted too


def test_expiry_parsing_handles_common_formats():
    from auth import parse_expiry
    assert parse_expiry("2030-01-01T00:00:00Z") == parse_expiry("2030-01-01T00:00:00")   # naive = UTC
    assert parse_expiry("2030-01-01T05:30:00+05:30") == parse_expiry("2030-01-01T00:00:00Z")
    assert parse_expiry(1893456000) == parse_expiry(1893456000000) == 1893456000            # s and ms


def test_brief_outage_does_not_sign_officer_out():
    mm, store = FakeMiniMoth(), SessionStore()
    handle = store.create(OFFICER, mm.verify_otp(OFFICER, "000000"))
    store.update(handle, expires_at=time.time() + 5)

    def down(token):
        raise MiniMothError("HTTP_503", status=503)

    mm.refresh = down
    assert ensure_fresh(mm, store, handle) is not None and store.get(handle)


# ---------- full sign-in flow through the real app ----------

@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_SESSIONS_FILE", str(tmp_path / "sessions.json"))   # never touch the real file
    from streamlit.testing.v1 import AppTest
    fake = FakeMiniMoth()
    for name in ("send_otp", "verify_otp", "validate", "refresh", "logout"):
        monkeypatch.setattr(auth.MiniMothClient, name, lambda self, *a, _n=name: getattr(fake, _n)(*a))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.secrets["MINIMOTH_API_KEY"] = "mm_test_dummy"
    at.secrets["AUTHORIZED_PHONES"] = OFFICER
    return at, fake


def _dashboard_shown(at):
    return any('<div class="statusbar">' in m.value for m in at.markdown)


def test_dashboard_is_locked_until_otp_is_verified(app):
    at, fake = app
    at.run()
    assert not _dashboard_shown(at) and not at.exception

    at.text_input[0].input("98765 43210")
    at.button[0].click().run()                                   # send code
    assert fake.sent == [OFFICER]

    at.text_input[0].input("123456")
    at.button[0].click().run()                                   # wrong code
    assert not _dashboard_shown(at) and any("Incorrect" in e.value for e in at.error)

    at.text_input[0].input("000000")
    at.button[0].click().run()                                   # right code
    assert _dashboard_shown(at) and not at.exception

    logout = next(b for b in at.button if b.label == "Log out")
    logout.click().run()
    assert not _dashboard_shown(at) and fake.logged_out


def test_numbers_off_the_allowlist_never_get_a_code(app):
    at, fake = app
    at.run()
    at.text_input[0].input(STRANGER)
    at.button[0].click().run()
    assert fake.sent == []                                       # no OTP sent, no credit spent
    at.text_input[0].input("000000")
    at.button[0].click().run()
    assert not _dashboard_shown(at)
