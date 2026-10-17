"""Phone OTP sign-in for the dashboard, using MiniMoth (https://minimoth.dev).

How it works:
- Only phone numbers on an allow-list (AUTHORIZED_PHONES) can request a code.
- MiniMoth sends a 6-digit code over WhatsApp, falling back to SMS.
- On a correct code MiniMoth returns an access token (5 min) and a refresh token.
  Both stay on the server. The browser only gets a random session handle in a
  cookie, so a page reload (or the light/dark switch) keeps the user signed in.
- Sessions are re-checked with MiniMoth every minute and refreshed before expiry;
  logout revokes the session at MiniMoth.

Configuration (Streamlit secrets or environment variables):
    MINIMOTH_API_KEY   mm_live_... (or mm_test_... for the sandbox: code is always 000000)
    AUTHORIZED_PHONES  comma-separated list, e.g. "+919876543210, 9123456789"
If MINIMOTH_API_KEY is not set, sign-in is disabled and the app runs in open demo mode.
"""
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API_BASE = "https://api.minimoth.dev"
USER_AGENT = "TracingTheSource/1.0 (+https://github.com/aayushdighegit/Tracing-the-Source-Demo)"
SESSION_COOKIE = "ts_session"
REVALIDATE_EVERY_S = 60          # re-check revocation with MiniMoth at most once a minute
REFRESH_MARGIN_S = 30            # refresh the access token this long before it expires
HANDLE_MAX_AGE_S = 10 * 24 * 3600  # matches MiniMoth's default refresh window

ERROR_MESSAGES = {
    "INVALID_PHONE": "That isn't a valid Indian mobile number.",
    "OTP_RATE_LIMITED": "Too many codes requested for this number. Please wait 10 minutes.",
    "OTP_NOT_FOUND": "That code has expired or was already used. Request a new one.",
    "INVALID_OTP": "Incorrect code. Please try again.",
    "INVALID_OTP_CODE": "The code must be exactly 6 digits.",
    "VERIFY_RATE_LIMITED": "Too many incorrect attempts. Request a new code.",
    "SMS_FAILED": "The code couldn't be delivered. Please try again in a moment.",
    "INSUFFICIENT_BALANCE": "Sign-in is temporarily unavailable (OTP credits exhausted).",
    "INVALID_API_KEY": "Sign-in is misconfigured (invalid API key).",
    "MISSING_API_KEY": "Sign-in is misconfigured (missing API key).",
    "SESSION_EXPIRED": "Your session has expired. Please sign in again.",
    "NETWORK_ERROR": "Couldn't reach the sign-in service. Check your connection and try again.",
    "NOT_AUTHORIZED": "This number isn't authorised to access the dashboard.",
}


class MiniMothError(Exception):
    def __init__(self, code, message="", status=None):
        super().__init__(message or code)
        self.code = code
        self.status = status

    @property
    def friendly(self):
        return ERROR_MESSAGES.get(self.code, f"Sign-in failed ({self.code}).")


def normalize_phone(raw):
    """Return the number as +91XXXXXXXXXX, or None if it isn't a valid Indian mobile number."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        return "+91" + digits
    return None


def parse_allowlist(value):
    """Accept a list or a comma/newline-separated string; return a set of normalised numbers."""
    items = value if isinstance(value, (list, tuple, set)) else re.split(r"[,\n;]", str(value or ""))
    return {p for p in (normalize_phone(i) for i in items) if p}


def mask_phone(phone):
    return f"+91 •••••• {phone[-4:]}" if phone and len(phone) >= 4 else "—"


def parse_expiry(value):
    """ISO-8601 timestamp -> epoch seconds (falls back to 5 minutes from now)."""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    except (TypeError, ValueError):
        return time.time() + 300


class MiniMothClient:
    """Minimal REST client for the MiniMoth OTP + session API (standard library only)."""

    def __init__(self, api_key, base_url=API_BASE, timeout=10, opener=None):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._open = opener or urllib.request.urlopen

    @property
    def is_sandbox(self):
        return str(self.api_key).startswith("mm_test_")

    def _request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base_url + path, data=data, method=method,
            # A named User-Agent is required: MiniMoth's Cloudflare blocks Python's default one (error 1010)
            headers={"X-Api-Key": self.api_key, "Content-Type": "application/json", "Accept": "application/json",
                     "User-Agent": USER_AGENT},
        )
        try:
            with self._open(req, timeout=self.timeout) as resp:
                raw = resp.read().decode() or "{}"
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read().decode() or "{}")
            except ValueError:
                payload = {}
            raise MiniMothError(payload.get("code", f"HTTP_{e.code}"), payload.get("error", ""), e.code) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise MiniMothError("NETWORK_ERROR", str(e)) from None

    def send_otp(self, phone):
        return self._request("POST", "/v1/otp/send", {"phone": phone})

    def verify_otp(self, phone, code):
        return self._request("POST", "/v1/otp/verify", {"phone": phone, "code": code})

    def validate(self, access_token):
        return self._request("POST", "/v1/session/validate", {"access_token": access_token})

    def refresh(self, refresh_token):
        return self._request("POST", "/v1/session/refresh", {"refresh_token": refresh_token})

    def logout(self, access_token):
        return self._request("POST", "/v1/session/logout", {"access_token": access_token})


class SessionStore:
    """Server-side session table: random handle -> MiniMoth tokens.

    Tokens never leave the server; the browser only holds the opaque handle.
    In-memory for this demo (one process); use Redis or a database in production.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions = {}

    def create(self, phone, tokens):
        handle = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[handle] = {
                "phone": phone,
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "expires_at": parse_expiry(tokens.get("expires_at")),
                "created_at": time.time(),
                "last_validated": time.time(),
            }
        return handle

    def get(self, handle):
        with self._lock:
            s = self._sessions.get(handle)
            if s and time.time() - s["created_at"] > HANDLE_MAX_AGE_S:
                self._sessions.pop(handle, None)
                return None
            return dict(s) if s else None

    def update(self, handle, **fields):
        with self._lock:
            if handle in self._sessions:
                self._sessions[handle].update(fields)

    def delete(self, handle):
        with self._lock:
            return self._sessions.pop(handle, None)


def ensure_fresh(client, store, handle):
    """Make sure the session behind `handle` is still valid. Returns the session dict or None.

    Refreshes the access token shortly before it expires (both tokens rotate) and
    re-checks revocation with MiniMoth at most once every REVALIDATE_EVERY_S seconds.
    """
    s = store.get(handle)
    if not s:
        return None
    now = time.time()
    try:
        if now >= s["expires_at"] - REFRESH_MARGIN_S:
            t = client.refresh(s["refresh_token"])
            store.update(handle, access_token=t.get("access_token"), refresh_token=t.get("refresh_token"),
                         expires_at=parse_expiry(t.get("expires_at")), last_validated=now)
        elif now - s["last_validated"] >= REVALIDATE_EVERY_S:
            if not client.validate(s["access_token"]).get("valid"):
                store.delete(handle)
                return None
            store.update(handle, last_validated=now)
    except MiniMothError as e:
        if e.code == "NETWORK_ERROR":
            return s  # keep the user signed in through a brief network blip; next run re-checks
        store.delete(handle)
        return None
    return store.get(handle)


def end_session(client, store, handle):
    """Revoke the session at MiniMoth (refreshing first if needed) and forget it locally."""
    s = store.delete(handle)
    if not s:
        return
    try:
        token = s["access_token"]
        if time.time() >= s["expires_at"] - 5:
            token = client.refresh(s["refresh_token"]).get("access_token")
        client.logout(token)
    except MiniMothError:
        pass  # the local session is gone either way
