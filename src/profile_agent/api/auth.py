"""Entra ID (Azure AD) authentication middleware using MSAL."""

from __future__ import annotations

import logging
from typing import Any

import msal
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer

from profile_agent.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)

# Module-level cache for the MSAL confidential client
_msal_app: msal.ConfidentialClientApplication | None = None


def _get_msal_app(settings: Settings) -> msal.ConfidentialClientApplication:
    global _msal_app
    if _msal_app is None:
        authority = f"https://login.microsoftonline.com/{settings.entra_tenant_id}"
        _msal_app = msal.ConfidentialClientApplication(
            client_id=settings.entra_client_id,
            client_credential=settings.entra_client_secret,
            authority=authority,
        )
    return _msal_app


async def validate_token(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Validate the Bearer token from the Authorization header.

    Returns the decoded token claims if valid.
    Raises 401 if missing/invalid.
    """
    if not settings.entra_client_id:
        # Auth not configured — allow anonymous in dev
        return {"sub": "anonymous", "name": "Anonymous User"}

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = auth_header[7:]
    app = _get_msal_app(settings)

    # Validate the token using MSAL's token cache / decode
    # In production, use the well-known OIDC endpoint to validate
    try:
        import jwt
        from jwt import PyJWKClient

        jwks_url = f"https://login.microsoftonline.com/{settings.entra_tenant_id}/discovery/v2.0/keys"
        jwks_client = PyJWKClient(jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.entra_client_id,
            issuer=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0",
        )
        return claims
    except Exception as e:
        logger.warning("Token validation failed: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user(claims: dict[str, Any] = Depends(validate_token)) -> dict[str, Any]:
    """Extract user info from validated token claims."""
    return {
        "user_id": claims.get("oid", claims.get("sub", "unknown")),
        "name": claims.get("name", "Unknown"),
        "email": claims.get("preferred_username", claims.get("email", "")),
    }
