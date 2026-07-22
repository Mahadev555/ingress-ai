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
    return context


async def require_admin(
    x_admin_token: Optional[str] = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=503,
            detail={"error": {"message": "admin API disabled (set ADMIN_API_KEY)", "type": "config_error"}},
        )
    if x_admin_token != settings.admin_api_key:
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "invalid admin token", "type": "auth_error"}},
        )
