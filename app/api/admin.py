from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
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


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(
    key_id: int, session: AsyncSession = Depends(get_session)
) -> Response:
    key = await session.get(VirtualKey, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="key not found")
    # Deactivate rather than delete so usage history stays intact.
    key.active = False
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Reusable token/cost aggregate columns (input, output, total, cost).
def _usage_aggregates():
    return (
        func.count(UsageRecord.id),
        func.coalesce(func.sum(UsageRecord.prompt_tokens), 0),
        func.coalesce(func.sum(UsageRecord.completion_tokens), 0),
        func.coalesce(func.sum(UsageRecord.total_tokens), 0),
        func.coalesce(func.sum(UsageRecord.cost_usd), 0.0),
    )


class UsageSummary(BaseModel):
    total_requests: int
    prompt_tokens: int  # input
    completion_tokens: int  # output
    total_tokens: int
    total_cost_usd: float


@router.get("/usage", response_model=UsageSummary)
async def usage_summary(session: AsyncSession = Depends(get_session)) -> UsageSummary:
    requests, prompt, completion, total, cost = (
        await session.execute(select(*_usage_aggregates()))
    ).one()
    return UsageSummary(
        total_requests=requests,
        prompt_tokens=int(prompt),
        completion_tokens=int(completion),
        total_tokens=int(total),
        total_cost_usd=round(float(cost), 6),
    )


class KeyUsage(BaseModel):
    key_id: int
    name: str
    key_prefix: str
    tenant_id: str
    requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    token_budget: Optional[int] = None


@router.get("/usage/by-key", response_model=list[KeyUsage])
async def usage_by_key(session: AsyncSession = Depends(get_session)) -> list[KeyUsage]:
    """Per-key usage: requests, input/output/total tokens, cost, and budget."""
    rows = (
        await session.execute(
            select(UsageRecord.key_id, *_usage_aggregates()).group_by(UsageRecord.key_id)
        )
    ).all()

    keys = {k.id: k for k in (await session.execute(select(VirtualKey))).scalars()}

    usage = [
        KeyUsage(
            key_id=key_id,
            name=(keys[key_id].name if key_id in keys else "(deleted key)"),
            key_prefix=(keys[key_id].key_prefix if key_id in keys else "—"),
            tenant_id=(keys[key_id].tenant_id if key_id in keys else "—"),
            requests=requests,
            prompt_tokens=int(prompt),
            completion_tokens=int(completion),
            total_tokens=int(total),
            cost_usd=round(float(cost), 6),
            token_budget=(keys[key_id].token_budget if key_id in keys else None),
        )
        for key_id, requests, prompt, completion, total, cost in rows
    ]
    usage.sort(key=lambda u: u.total_tokens, reverse=True)
    return usage


class ModelUsage(BaseModel):
    model: str
    provider: str
    requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


@router.get("/usage/by-model", response_model=list[ModelUsage])
async def usage_by_model(session: AsyncSession = Depends(get_session)) -> list[ModelUsage]:
    """Per-model usage: requests, input/output/total tokens, and cost."""
    rows = (
        await session.execute(
            select(UsageRecord.model, UsageRecord.provider, *_usage_aggregates()).group_by(
                UsageRecord.model, UsageRecord.provider
            )
        )
    ).all()

    usage = [
        ModelUsage(
            model=model,
            provider=provider,
            requests=requests,
            prompt_tokens=int(prompt),
            completion_tokens=int(completion),
            total_tokens=int(total),
            cost_usd=round(float(cost), 6),
        )
        for model, provider, requests, prompt, completion, total, cost in rows
    ]
    usage.sort(key=lambda u: u.total_tokens, reverse=True)
    return usage
