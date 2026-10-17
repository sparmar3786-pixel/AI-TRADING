"""Authentication helpers for the single-owner signals API.

Legacy device-ID-only mode exists solely for staged migration. Production should
set API_AUTH_MODE=required and configure API_ACCESS_KEY (>=32 random characters)
or Firebase project ID + an explicit AUTH_ALLOWED_UIDS allow-list. A client
device ID is never treated as proof of identity.
"""
from __future__ import annotations

import hmac
import os
from typing import Any


class AuthConfigurationError(RuntimeError):
    pass


class AuthenticationError(PermissionError):
    pass


def _csv_set(name: str) -> set[str]:
    return {value.strip() for value in os.getenv(name, "").split(",") if value.strip()}


def authenticate_request(authorization: str = "", access_key: str = "") -> dict[str, Any]:
    mode = os.getenv("API_AUTH_MODE", "legacy").strip().lower()
    if mode not in {"legacy", "required", "strict", "access_key", "firebase"}:
        raise AuthConfigurationError("API_AUTH_MODE must be legacy or required.")

    configured_key = (os.getenv("API_ACCESS_KEY") or os.getenv("BACKEND_ACCESS_KEY") or "").strip()
    firebase_project = (os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
    allowed_uids = _csv_set("AUTH_ALLOWED_UIDS")
    required = mode in {"required", "strict", "access_key", "firebase"}

    if configured_key:
        if len(configured_key) < 32:
            raise AuthConfigurationError("API_ACCESS_KEY must contain at least 32 characters.")
        if access_key and hmac.compare_digest(access_key, configured_key):
            return {"method": "access_key", "subject": "single-owner"}

    token = ""
    parts = (authorization or "").strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1].strip()

    if token:
        if not firebase_project:
            if required:
                raise AuthConfigurationError("Firebase token verification requires FIREBASE_PROJECT_ID.")
        elif not allowed_uids:
            if required:
                raise AuthConfigurationError("Firebase bearer auth requires an explicit AUTH_ALLOWED_UIDS allow-list.")
        else:
            try:
                from google.auth.transport.requests import Request
                from google.oauth2.id_token import verify_firebase_token

                claims = verify_firebase_token(token, Request(), audience=firebase_project)
                uid = str((claims or {}).get("user_id") or (claims or {}).get("sub") or "").strip()
                if not uid or uid not in allowed_uids:
                    raise AuthenticationError("Authenticated user is not authorized for this private trading service.")
                return {"method": "firebase_id_token", "subject": uid}
            except AuthenticationError:
                raise
            except Exception as exc:
                raise AuthenticationError("Firebase bearer token is invalid or expired.") from exc

    if required:
        if not configured_key and not (firebase_project and allowed_uids):
            raise AuthConfigurationError("Configure API_ACCESS_KEY or Firebase verification and AUTH_ALLOWED_UIDS before enabling required auth.")
        raise AuthenticationError("Missing or invalid API access key or Firebase bearer token.")

    # Temporary compatibility mode; X-Device-Id validation happens in the API
    # layer. Deployments should migrate and then switch API_AUTH_MODE=required.
    if configured_key:
        raise AuthenticationError("Missing or invalid API access key.")
    return {"method": "legacy_device_id", "subject": None}
