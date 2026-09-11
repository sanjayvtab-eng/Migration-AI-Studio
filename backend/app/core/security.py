from __future__ import annotations
import hashlib, hmac, os, re
from datetime import datetime, timedelta, timezone
import jwt
from .config import get_settings

SECRET_PATTERNS = [re.compile(p, re.I) for p in [r"token\s*=\s*[^\s,;]+", r"password\s*=\s*[^\s,;]+", r"jwt_secret\s*=\s*[^\s,;]+", r"api[_-]?key\s*=\s*[^\s,;]+"]]

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310000)
    return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        alg, rounds, salt_hex, digest_hex = encoded.split("$", 3)
        if alg != "pbkdf2_sha256": return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)).hex()
        return hmac.compare_digest(calc, digest_hex)
    except Exception:
        return False

def create_access_token(subject: str, role: str) -> str:
    s = get_settings(); now = datetime.now(timezone.utc)
    return jwt.encode({"sub": subject, "role": role, "iat": now, "exp": now + timedelta(minutes=s.access_token_minutes)}, s.jwt_secret, algorithm=s.jwt_algorithm)

def decode_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])

def mask_secrets(text: str) -> str:
    out = text
    for pattern in SECRET_PATTERNS:
        out = pattern.sub(lambda m: m.group(0).split("=")[0] + "=***", out)
    return out
