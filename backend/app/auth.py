"""JWT and password helpers for pilot authentication."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional


class AuthError(ValueError):
    pass


def hash_password(password: str) -> str:
    try:
        import bcrypt  # type: ignore

        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    except Exception:
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
        return "pbkdf2_sha256$210000${salt}${digest}".format(
            salt=base64.urlsafe_b64encode(salt).decode("ascii"),
            digest=base64.urlsafe_b64encode(digest).decode("ascii"),
        )


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    if password_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt_b64, digest_b64 = password_hash.split("$", 3)
            salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
            expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
            return hmac.compare_digest(actual, expected)
        except Exception:
            return False
    try:
        import bcrypt  # type: ignore

        return bool(bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8")))
    except Exception:
        return False


def create_access_token(
    *,
    user_id: str,
    clinic_id: str,
    role: str,
    secret_key: Optional[str] = None,
    expires_minutes: int = 8 * 60,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "clinic_id": clinic_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    secret = secret_key or _secret_key()
    try:
        import jwt  # type: ignore

        return jwt.encode(payload, secret, algorithm="HS256")
    except Exception:
        return _encode_hs256(payload, secret)


def decode_access_token(token: str, *, secret_key: Optional[str] = None) -> dict[str, Any]:
    secret = secret_key or _secret_key()
    try:
        import jwt  # type: ignore

        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except Exception:
        payload = _decode_hs256(token, secret)
    if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        raise AuthError("Token süresi dolmuş.")
    if not payload.get("sub") or not payload.get("clinic_id"):
        raise AuthError("Token eksik kimlik bilgisi taşıyor.")
    return payload


def _secret_key() -> str:
    secret = os.environ.get("SECRET_KEY", "").strip()
    if secret:
        return secret
    if os.environ.get("KLINIA_AUTH_MODE", "dev").strip().lower() == "dev":
        return "dev-only-change-me"
    raise AuthError("SECRET_KEY tanımlı değil.")


def _encode_hs256(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = ".".join((_b64_json(header), _b64_json(payload)))
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64_bytes(signature)}"


def _decode_hs256(token: str, secret: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".", 2)
        signing_input = f"{header_b64}.{payload_b64}"
        expected = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
        actual = _unb64(signature_b64)
        if not hmac.compare_digest(actual, expected):
            raise AuthError("Token imzası geçersiz.")
        header = json.loads(_unb64(header_b64))
        if header.get("alg") != "HS256":
            raise AuthError("Token algoritması desteklenmiyor.")
        return json.loads(_unb64(payload_b64))
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError("Token doğrulanamadı.") from exc


def _b64_json(value: dict[str, Any]) -> str:
    return _b64_bytes(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _b64_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))
