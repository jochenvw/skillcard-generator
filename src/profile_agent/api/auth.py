"""Entra ID (Azure AD) authentication — JWT validation for SPA access tokens."""

from __future__ import annotations

import logging
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from jwt import PyJWKClient

from profile_agent.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Module-level JWKS client cache (thread-safe, handles key rotation)
_jwks_client: PyJWKClient | None = None


def _get_jwks_client(tenant_id: str) -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_client


@router.get("/config")
async def auth_config(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Public endpoint — returns auth configuration for the SPA."""
    if not settings.entra_client_id or not settings.entra_tenant_id:
        return {"authEnabled": False}

    return {
        "authEnabled": True,
        "clientId": settings.entra_client_id,
        "authority": f"https://login.microsoftonline.com/{settings.entra_tenant_id}",
        "apiScopes": [f"api://{settings.entra_client_id}/access_as_user"],
    }


async def validate_token(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Validate the Bearer access token from the Authorization header.

    Returns the decoded token claims if valid.
    In dev mode with auth bypass enabled, allows anonymous access.
    In all other cases, requires a valid token — fails closed.
    """
    if not settings.entra_client_id:
        if settings.is_dev and settings.dev_auth_bypass:
            return {"sub": "anonymous", "name": "Anonymous User", "preferred_username": "dev@localhost"}
        if settings.is_dev:
            logger.warning("Auth not configured. Set ENTRA_CLIENT_ID or enable DEV_AUTH_BYPASS=true.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication not configured")

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = auth_header[7:]

    try:
        jwks_client = _get_jwks_client(settings.entra_tenant_id)
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.entra_client_id,
            issuer=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0",
        )
        return claims
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from None
    except jwt.InvalidAudienceError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid audience") from None
    except jwt.InvalidIssuerError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid issuer") from None
    except Exception as e:
        logger.warning("Token validation failed: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from None


async def get_current_user(claims: dict[str, Any] = Depends(validate_token)) -> dict[str, Any]:
    """Extract user info from validated token claims."""
    return {
        "user_id": claims.get("oid", claims.get("sub", "unknown")),
        "name": claims.get("name", "Unknown"),
        "email": claims.get("preferred_username", claims.get("email", "")),
    }
