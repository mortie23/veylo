import json
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple
import jwt
from jwt.algorithms import RSAAlgorithm
import requests

logger = logging.getLogger(__name__)

# Cache for Microsoft Entra ID OpenID configuration and JWKS public keys
_JWKS_CACHE: Dict[str, Any] = {"keys": [], "expires_at": 0}

ENTRA_TENANT_ID = os.environ.get("ENTRA_TENANT_ID", "d63e78bd-9ee3-4a7d-a868-738824c13bd1")
API_AUDIENCE = os.environ.get("API_AUDIENCE", "api://func-vey-portal-dev")
BACKEND_API_CLIENT_ID = os.environ.get("BACKEND_API_CLIENT_ID", "926dc2b5-dee7-49af-a416-f2ed27f6b6c0")


def _get_signing_keys(tenant_id: str) -> list:
    """Fetch and cache public signing keys from Entra ID JWKS endpoints."""
    now = time.time()
    if _JWKS_CACHE["keys"] and now < _JWKS_CACHE["expires_at"]:
        return _JWKS_CACHE["keys"]

    urls = []
    if tenant_id:
        urls.append(f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys")
    urls.append("https://login.microsoftonline.com/common/discovery/keys")

    all_keys = []
    for jwks_url in urls:
        try:
            response = requests.get(jwks_url, timeout=10)
            if response.ok:
                data = response.json()
                keys = data.get("keys", [])
                all_keys.extend(keys)
        except Exception as ex:
            logger.warning(f"Failed to fetch JWKS from {jwks_url}: {ex}")

    if all_keys:
        # Cache keys for 1 hour
        _JWKS_CACHE["keys"] = all_keys
        _JWKS_CACHE["expires_at"] = now + 3600

    return all_keys


def validate_jwt_token(auth_header: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Validate Entra ID JWT Bearer Token.
    Verifies signature, audience, issuer, and expiration.
    Returns (decoded_claims, None) on success, or (None, error_message) on failure.
    """
    if not auth_header:
        msg = "Missing Authorization header."
        logger.warning(msg)
        return None, msg

    parts = auth_header.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        msg = "Invalid Authorization header format. Expected 'Bearer <token>'."
        logger.warning(msg)
        return None, msg

    token = parts[1]

    tenant_id = os.environ.get("ENTRA_TENANT_ID") or ENTRA_TENANT_ID
    audience = os.environ.get("API_AUDIENCE") or API_AUDIENCE
    backend_client_id = os.environ.get("BACKEND_API_CLIENT_ID") or BACKEND_API_CLIENT_ID

    # Local development bypass: if bypass mode is explicitly enabled
    if os.environ.get("DEV_AUTH_BYPASS", "").lower() in ("true", "1") and token == "dev-mock-token":
        logger.warning("DEV_AUTH_BYPASS is active: using mock user claims.")
        return {
            "sub": "mock-dev-user-id",
            "oid": "mock-dev-oid",
            "preferred_username": "developer@local.test",
            "contact_id": "00000000-0000-0000-0000-000000000001",
            "roles": ["File.Upload"]
        }, None

    try:
        # Inspect unverified header and payload for diagnostics
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            msg = "Token header missing 'kid'."
            logger.warning(msg)
            return None, msg

        unverified_claims = jwt.decode(token, options={"verify_signature": False})
        token_aud = unverified_claims.get("aud")
        token_iss = unverified_claims.get("iss")

        keys = _get_signing_keys(tenant_id)
        matching_jwk = next((k for k in keys if k.get("kid") == kid), None)
        if not matching_jwk:
            msg = f"No matching JWK key found for kid: {kid} (fetched {len(keys)} keys)"
            logger.warning(msg)
            return None, msg

        public_key = RSAAlgorithm.from_jwk(json.dumps(matching_jwk))

        valid_issuers = [
            f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            f"https://login.microsoftonline.com/{tenant_id}/v2.0/",
            f"https://login.microsoftonline.com/{tenant_id}",
            f"https://login.microsoftonline.com/{tenant_id}/",
            f"https://sts.windows.net/{tenant_id}/",
            f"https://sts.windows.net/{tenant_id}",
        ]

        valid_audiences = list(filter(None, {
            audience,
            "api://func-vey-portal-dev",
            backend_client_id,
            "926dc2b5-dee7-49af-a416-f2ed27f6b6c0",
            "5a7e8db6-561b-4a60-aed2-f0c652661f0d"
        }))

        # Decode and validate token
        claims = jwt.decode(
            token,
            key=public_key,
            algorithms=["RS256"],
            audience=valid_audiences,
            issuer=valid_issuers,
            options={"verify_exp": True, "verify_aud": True, "verify_iss": True},
        )

        # Normalize user contact / subject identifier
        claims["contact_id"] = claims.get("extension_ContactId") or claims.get("contact_id") or claims.get("oid")
        return claims, None

    except jwt.ExpiredSignatureError:
        msg = "Bearer token has expired."
        logger.warning(msg)
        return None, msg
    except jwt.InvalidAudienceError as ex:
        msg = f"Invalid token audience '{token_aud}'. Expected one of: {valid_audiences} ({ex})"
        logger.warning(msg)
        return None, msg
    except jwt.InvalidIssuerError as ex:
        msg = f"Invalid token issuer '{token_iss}'. Expected one of: {valid_issuers} ({ex})"
        logger.warning(msg)
        return None, msg
    except jwt.InvalidTokenError as ex:
        msg = f"Invalid JWT bearer token: {ex}"
        logger.warning(msg)
        return None, msg
    except Exception as ex:
        msg = f"Unexpected error validating JWT token: {ex}"
        logger.exception(msg)
        return None, msg
