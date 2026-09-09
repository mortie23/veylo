import json
import logging
import os
import time
from typing import Any, Dict, Optional
import jwt
from jwt.algorithms import RSAAlgorithm
import requests

logger = logging.getLogger(__name__)

# Cache for Microsoft Entra ID OpenID configuration and JWKS public keys
_JWKS_CACHE: Dict[str, Any] = {"keys": [], "expires_at": 0}

ENTRA_TENANT_ID = os.environ.get("ENTRA_TENANT_ID", "")
API_AUDIENCE = os.environ.get("API_AUDIENCE", "")


def _get_signing_keys(tenant_id: str) -> list:
    """Fetch and cache public signing keys from Entra ID JWKS endpoint."""
    now = time.time()
    if _JWKS_CACHE["keys"] and now < _JWKS_CACHE["expires_at"]:
        return _JWKS_CACHE["keys"]

    if not tenant_id:
        logger.warning("ENTRA_TENANT_ID not configured.")
        return []

    jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    try:
        response = requests.get(jwks_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        keys = data.get("keys", [])
        # Cache keys for 1 hour
        _JWKS_CACHE["keys"] = keys
        _JWKS_CACHE["expires_at"] = now + 3600
        return keys
    except Exception as ex:
        logger.error(f"Failed to fetch JWKS from {jwks_url}: {ex}")
        return []


def validate_jwt_token(auth_header: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Validate Entra ID JWT Bearer Token.
    Verifies signature, audience, issuer, and expiration.
    Returns decoded claims dict on success, None on failure.
    """
    if not auth_header:
        logger.warning("Missing Authorization header.")
        return None

    parts = auth_header.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("Invalid Authorization header format. Expected 'Bearer <token>'.")
        return None

    token = parts[1]

    tenant_id = os.environ.get("ENTRA_TENANT_ID", ENTRA_TENANT_ID)
    audience = os.environ.get("API_AUDIENCE", API_AUDIENCE)

    # Local development bypass: if bypass mode is explicitly enabled
    if os.environ.get("DEV_AUTH_BYPASS", "").lower() in ("true", "1") and token == "dev-mock-token":
        logger.warning("DEV_AUTH_BYPASS is active: using mock user claims.")
        return {
            "sub": "mock-dev-user-id",
            "oid": "mock-dev-oid",
            "preferred_username": "developer@local.test",
            "contact_id": "00000000-0000-0000-0000-000000000001",
            "roles": ["File.Upload"]
        }

    try:
        # Extract kid from unverified token header
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            logger.warning("Token header missing 'kid'.")
            return None

        keys = _get_signing_keys(tenant_id)
        matching_jwk = next((k for k in keys if k.get("kid") == kid), None)
        if not matching_jwk:
            logger.warning(f"No matching JWK key found for kid: {kid}")
            return None

        public_key = RSAAlgorithm.from_jwk(json.dumps(matching_jwk))

        valid_issuers = [
            f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            f"https://sts.windows.net/{tenant_id}/",
        ]

        # Decode and validate token
        claims = jwt.decode(
            token,
            key=public_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=valid_issuers,
            options={"verify_exp": True, "verify_aud": True, "verify_iss": True},
        )

        # Normalize user contact / subject identifier
        claims["contact_id"] = claims.get("extension_ContactId") or claims.get("contact_id") or claims.get("oid")
        return claims

    except jwt.ExpiredSignatureError:
        logger.warning("Bearer token has expired.")
        return None
    except jwt.InvalidTokenError as ex:
        logger.warning(f"Invalid JWT bearer token: {ex}")
        return None
    except Exception as ex:
        logger.exception(f"Unexpected error validating JWT token: {ex}")
        return None
