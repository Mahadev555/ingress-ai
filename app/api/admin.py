from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.auth import generate_key
from app.db.models import UsageRecord, VirtualKey
from app.db.session import get_session

router = APIRouter(dependencies=[Depends(require_admin)])


class CreateKeyRequest(BaseModel):
    name: str = ""
    tenant_id: str = "default"
    allowed_models: list[str] = Field(default_factory=list)
    token_budget: Optional[int] = None


class CreateKeyResponse(BaseModel):
    id: int
    key: str  # full virtual key, shown only once
    key_prefix: str
    name: str
    tenant_id: str
    allowed_models: list[str]
    token_budget: Optional[int]


class KeyInfo(BaseModel):
    id: int
    key_prefix: str
    name: str
    tenant_id: str
    allowed_models: list[str]
    token_budget: Optional[int]
    active: bool


@router.post("/keys", response_model=CreateKeyResponse)
async def create_key(
    body: CreateKeyRequest,
    session: AsyncSession = Depends(get_session),
) -> CreateKeyResponse:
    full_key, prefix, key_hash = generate_key()

    key = VirtualKey(
        name=body.name,
        key_prefix=prefix,
        key_hash=key_hash,
        tenant_id=body.tenant_id,
        allowed_models=body.allowed_models,
        token_budget=body.token_budget,
    )
    session.add(key)
    await session.commit()
    await session.refresh(key)

    return CreateKeyResponse(
        id=key.id,
        key=full_key,
        key_prefix=prefix,
        name=key.name,
        tenant_id=key.tenant_id,
        allowed_models=list(key.allowed_models or []),
        token_budget=key.token_budget,
    )


@router.get("/keys", response_model=list[KeyInfo])
async def list_keys(session: AsyncSession = Depends(get_session)) -> list[KeyInfo]:
    result = await session.execute(select(VirtualKey).order_by(VirtualKey.id))
    return [
        KeyInfo(
            id=key.id,
            key_prefix=key.key_prefix,
            name=key.name,
            tenant_id=key.tenant_id,
            allowed_models=list(key.allowed_models or []),
            token_budget=key.token_budget,
            active=key.active,
        )
        for key in result.scalars()
    ]


class UsageSummary(BaseModel):
    total_requests: int
    total_tokens: int
    total_cost_usd: float


@router.get("/usage", response_model=UsageSummary)
async def usage_summary(session: AsyncSession = Depends(get_session)) -> UsageSummary:
    row = (
        await session.execute(
            select(
                func.count(UsageRecord.id),
                func.coalesce(func.sum(UsageRecord.total_tokens), 0),
                func.coalesce(func.sum(UsageRecord.cost_usd), 0.0),
            )
        )
    ).one()
    return UsageSummary(
        total_requests=row[0],
        total_tokens=int(row[1]),
        total_cost_usd=round(float(row[2]), 6),
    )
