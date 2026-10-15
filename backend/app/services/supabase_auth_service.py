from __future__ import annotations

import logging
from datetime import datetime, timezone
import httpx
from app.core.config import get_settings
from app.core.security import verify_password

logger = logging.getLogger(__name__)


def _get_supabase_client() -> tuple[str, dict[str, str]] | None:
    settings = get_settings()
    base_url = settings.supabase_url
    api_key = settings.supabase_service_role_key or settings.supabase_anon_key

    if not base_url or not api_key:
        return None

    clean_url = base_url.rstrip("/")
    if not clean_url.endswith("/rest/v1"):
        clean_url += "/rest/v1"

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    return clean_url, headers


def get_user_by_email(email: str) -> dict | None:
    client_info = _get_supabase_client()
    if not client_info:
        return None

    clean_url, headers = client_info
    email_clean = email.strip().lower()

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{clean_url}/app_users",
                headers=headers,
                params={"email": f"ilike.{email_clean}", "limit": 1},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    return data[0]
    except Exception as exc:
        logger.error(f"Error querying Supabase app_users for {email}: {exc}")

    return None


def upsert_user_otp(email: str, otp_code: str, expires_at: datetime) -> bool:
    client_info = _get_supabase_client()
    if not client_info:
        return False

    clean_url, headers = client_info
    email_clean = email.strip().lower()
    existing = get_user_by_email(email_clean)

    payload = {
        "email": email_clean,
        "otp_code": otp_code,
        "otp_expires_at": expires_at.isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            if existing:
                resp = client.patch(
                    f"{clean_url}/app_users",
                    headers=headers,
                    params={"email": f"ilike.{email_clean}"},
                    json=payload,
                )
            else:
                payload["is_verified"] = False
                payload["role"] = "User"
                resp = client.post(
                    f"{clean_url}/app_users",
                    headers=headers,
                    json=payload,
                )
            return resp.status_code in (200, 201, 204)
    except Exception as exc:
        logger.error(f"Error saving OTP in Supabase for {email}: {exc}")
        return False


def verify_user_otp(email: str, otp_code: str) -> tuple[bool, str]:
    user = get_user_by_email(email)
    if not user:
        return False, "No account found for this email"

    saved_otp = user.get("otp_code")
    expires_str = user.get("otp_expires_at")

    if not saved_otp:
        return False, "No pending OTP verification code found"

    if expires_str:
        try:
            expires_dt = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
            if expires_dt < datetime.now(timezone.utc):
                return False, "OTP code has expired. Please request a new code."
        except Exception:
            pass

    if saved_otp.strip() != otp_code.strip():
        return False, "Invalid verification code"

    client_info = _get_supabase_client()
    if client_info:
        clean_url, headers = client_info
        email_clean = email.strip().lower()
        try:
            with httpx.Client(timeout=10.0) as client:
                client.patch(
                    f"{clean_url}/app_users",
                    headers=headers,
                    params={"email": f"ilike.{email_clean}"},
                    json={
                        "is_verified": True,
                        "otp_code": None,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
        except Exception as exc:
            logger.error(f"Error updating verified status in Supabase: {exc}")

    return True, "Email verified successfully"


def set_user_password(email: str, password_hash: str) -> bool:
    client_info = _get_supabase_client()
    if not client_info:
        return False

    clean_url, headers = client_info
    email_clean = email.strip().lower()

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.patch(
                f"{clean_url}/app_users",
                headers=headers,
                params={"email": f"ilike.{email_clean}"},
                json={
                    "password_hash": password_hash,
                    "is_verified": True,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            return resp.status_code in (200, 204)
    except Exception as exc:
        logger.error(f"Error setting password in Supabase for {email}: {exc}")
        return False


def authenticate_app_user(identifier: str, password: str) -> dict | None:
    user = get_user_by_email(identifier)
    if not user:
        return None

    pwd_hash = user.get("password_hash")
    if not pwd_hash:
        return None

    if verify_password(password, pwd_hash):
        return user

    return None
