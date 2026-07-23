from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import KeyContext, resolve_key
from app.core.config import Settings, get_settings
from app.db.session import get_session


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


async def require_key(
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> KeyContext:
    context = await resolve_key(session, _bearer_token(authorization))
    if context is None:
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "invalid or missing virtual key", "type": "auth_error"}},
        )
    if context.is_expired():
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "this virtual key has expired", "type": "key_expired"}},
        )
    return context


def _split(csv: str) -> set[str]:
    return {t.strip() for t in csv.split(",") if t.strip()}


def _write_tokens(settings: Settings) -> set[str]:
    tokens = _split(settings.admin_tokens)
    if settings.admin_api_key:
        tokens.add(settings.admin_api_key)
    return tokens


def _read_tokens(settings: Settings) -> set[str]:
    return _write_tokens(settings) | _split(settings.admin_read_tokens)


def require_admin(
    x_admin_token: Optional[str] = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Full-admin (write) access: the primary key or any admin_tokens entry."""
    write = _write_tokens(settings)
    if not write:
        raise HTTPException(
            status_code=503,
            detail={"error": {"message": "admin API disabled (set ADMIN_API_KEY)", "type": "config_error"}},
        )
    if x_admin_token not in write:
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "invalid admin token", "type": "auth_error"}},
        )


def require_admin_read(
    x_admin_token: Optional[str] = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Read access: any full-admin token or a read-only admin_read_tokens entry."""
    allowed = _read_tokens(settings)
    if not allowed:
        raise HTTPException(
            status_code=503,
            detail={"error": {"message": "admin API disabled (set ADMIN_API_KEY)", "type": "config_error"}},
        )
    if x_admin_token not in allowed:
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "invalid admin token", "type": "auth_error"}},
        )
