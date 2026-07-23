from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin, require_admin_read
from app.core.auth import generate_key
from app.db.models import AuditLog, ModelConfig, UsageRecord, VirtualKey
from app.db.session import get_session

# Reads require any admin token (incl. read-only); writes add require_admin.
router = APIRouter(dependencies=[Depends(require_admin_read)])
_WRITE = [Depends(require_admin)]


class CreateKeyRequest(BaseModel):
    name: str = ""
    tenant_id: str = "default"
    allowed_models: list[str] = Field(default_factory=list)
    token_budget: Optional[int] = None
    cost_budget_usd: Optional[float] = None
    budget_period: str = "total"  # "total" | "daily" | "monthly"
    rate_limit_per_minute: Optional[int] = None
    tpm_limit: Optional[int] = None
    max_concurrency: Optional[int] = None
    expires_at: Optional[datetime] = None


class UpdateKeyRequest(BaseModel):
    """All fields optional; only those present are changed. Send an explicit
    null to clear a nullable field (e.g. token_budget)."""

    name: Optional[str] = None
    allowed_models: Optional[list[str]] = None
    token_budget: Optional[int] = None
    cost_budget_usd: Optional[float] = None
    budget_period: Optional[str] = None
    rate_limit_per_minute: Optional[int] = None
    tpm_limit: Optional[int] = None
    max_concurrency: Optional[int] = None
    expires_at: Optional[datetime] = None


class KeyInfo(BaseModel):
    id: int
    key_prefix: str
    name: str
    tenant_id: str
    allowed_models: list[str]
    token_budget: Optional[int]
    cost_budget_usd: Optional[float]
    budget_period: str
    rate_limit_per_minute: Optional[int]
    tpm_limit: Optional[int]
    max_concurrency: Optional[int]
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    active: bool


class CreateKeyResponse(KeyInfo):
    key: str  # full virtual key, shown only once


@router.post("/keys", response_model=CreateKeyResponse, dependencies=_WRITE)
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
        cost_budget_usd=body.cost_budget_usd,
        budget_period=body.budget_period,
        rate_limit_per_minute=body.rate_limit_per_minute,
        tpm_limit=body.tpm_limit,
        max_concurrency=body.max_concurrency,
        expires_at=body.expires_at,
    )
    session.add(key)
    await session.commit()
    await session.refresh(key)

    return CreateKeyResponse(**_key_info(key).model_dump(), key=full_key)


def _key_info(key: VirtualKey) -> KeyInfo:
    return KeyInfo(
        id=key.id,
        key_prefix=key.key_prefix,
        name=key.name,
        tenant_id=key.tenant_id,
        allowed_models=list(key.allowed_models or []),
        token_budget=key.token_budget,
        cost_budget_usd=key.cost_budget_usd,
        budget_period=key.budget_period or "total",
        rate_limit_per_minute=key.rate_limit_per_minute,
        tpm_limit=key.tpm_limit,
        max_concurrency=key.max_concurrency,
        expires_at=key.expires_at,
        last_used_at=key.last_used_at,
        active=key.active,
    )


@router.get("/keys", response_model=list[KeyInfo])
async def list_keys(session: AsyncSession = Depends(get_session)) -> list[KeyInfo]:
    result = await session.execute(select(VirtualKey).order_by(VirtualKey.id))
    return [_key_info(key) for key in result.scalars()]


@router.patch("/keys/{key_id}", response_model=KeyInfo, dependencies=_WRITE)
async def update_key(
    key_id: int,
    body: UpdateKeyRequest,
    session: AsyncSession = Depends(get_session),
) -> KeyInfo:
    key = await session.get(VirtualKey, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="key not found")
    # Only apply fields the client actually sent (exclude_unset), so omitting a
    # field leaves it unchanged while sending null clears it.
    for field_name, value in body.model_dump(exclude_unset=True).items():
        setattr(key, field_name, value)
    await session.commit()
    await session.refresh(key)
    return _key_info(key)


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=_WRITE)
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
async def usage_summary(
    days: int = 0, session: AsyncSession = Depends(get_session)
) -> UsageSummary:
    """Totals across all keys/models. `days<=0` means all time."""
    days = min(days, 365)
    query = select(*_usage_aggregates())
    if days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.where(UsageRecord.created_at >= cutoff)
    requests, prompt, completion, total, cost = (await session.execute(query)).one()
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


class RecentRequest(BaseModel):
    id: int
    created_at: Optional[datetime]
    key_prefix: str
    provider: str
    model: str
    total_tokens: int
    cost_usd: float
    latency_ms: int
    status: int
    cache_hit: bool


@router.get("/usage/recent", response_model=list[RecentRequest])
async def usage_recent(
    limit: int = 20, session: AsyncSession = Depends(get_session)
) -> list[RecentRequest]:
    """Most recent requests, newest first — powers the live activity feed."""
    limit = max(1, min(limit, 200))
    rows = (
        await session.execute(
            select(UsageRecord).order_by(UsageRecord.id.desc()).limit(limit)
        )
    ).scalars().all()

    keys = {k.id: k for k in (await session.execute(select(VirtualKey))).scalars()}

    return [
        RecentRequest(
            id=r.id,
            created_at=r.created_at,
            key_prefix=(keys[r.key_id].key_prefix if r.key_id in keys else "—"),
            provider=r.provider,
            model=r.model,
            total_tokens=r.total_tokens,
            cost_usd=round(float(r.cost_usd), 6),
            latency_ms=r.latency_ms,
            status=r.status,
            cache_hit=r.cache_hit,
        )
        for r in rows
    ]


class TimeseriesPoint(BaseModel):
    day: str  # YYYY-MM-DD (UTC)
    model: str
    provider: str
    status: int
    requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


@router.get("/usage/timeseries", response_model=list[TimeseriesPoint])
async def usage_timeseries(
    days: int = 14, session: AsyncSession = Depends(get_session)
) -> list[TimeseriesPoint]:
    """Daily usage grouped by (day, model, provider, status).

    Returned flat so the dashboard can pivot it into per-model token lines, a
    requests/success-rate chart, and an errors-by-status chart. `func.date()`
    buckets by day on both SQLite (dev) and Postgres (prod).
    """
    days = min(days, 365)  # days <= 0 means "all time" (no lower bound)
    day = func.date(UsageRecord.created_at).label("day")

    query = (
        select(
            day,
            UsageRecord.model,
            UsageRecord.provider,
            UsageRecord.status,
            *_usage_aggregates(),
        )
        .group_by(day, UsageRecord.model, UsageRecord.provider, UsageRecord.status)
        .order_by(day)
    )
    if days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.where(UsageRecord.created_at >= cutoff)

    rows = (await session.execute(query)).all()

    return [
        TimeseriesPoint(
            day=str(d),
            model=model,
            provider=provider,
            status=st,
            requests=requests,
            prompt_tokens=int(prompt),
            completion_tokens=int(completion),
            total_tokens=int(total),
            cost_usd=round(float(cost), 6),
        )
        for d, model, provider, st, requests, prompt, completion, total, cost in rows
    ]


# --- model registry ----------------------------------------------------------


class ModelConfigRequest(BaseModel):
    name: str
    provider: str
    alias_of: Optional[str] = None
    input_price_per_1m: Optional[float] = None
    output_price_per_1m: Optional[float] = None
    default_rate_limit_per_minute: Optional[int] = None
    default_tpm_limit: Optional[int] = None
    enabled: bool = True


class ModelConfigUpdate(BaseModel):
    provider: Optional[str] = None
    alias_of: Optional[str] = None
    input_price_per_1m: Optional[float] = None
    output_price_per_1m: Optional[float] = None
    default_rate_limit_per_minute: Optional[int] = None
    default_tpm_limit: Optional[int] = None
    enabled: Optional[bool] = None


class ModelConfigInfo(BaseModel):
    id: int
    name: str
    provider: str
    alias_of: Optional[str]
    input_price_per_1m: Optional[float]
    output_price_per_1m: Optional[float]
    default_rate_limit_per_minute: Optional[int]
    default_tpm_limit: Optional[int]
    enabled: bool


def _model_info(m: ModelConfig) -> ModelConfigInfo:
    return ModelConfigInfo(
        id=m.id,
        name=m.name,
        provider=m.provider,
        alias_of=m.alias_of,
        input_price_per_1m=m.input_price_per_1m,
        output_price_per_1m=m.output_price_per_1m,
        default_rate_limit_per_minute=m.default_rate_limit_per_minute,
        default_tpm_limit=m.default_tpm_limit,
        enabled=m.enabled,
    )


async def _reload_registry(request: Request) -> None:
    await request.app.state.model_registry.reload(request.app.state.session_factory)


@router.get("/models", response_model=list[ModelConfigInfo])
async def list_model_configs(session: AsyncSession = Depends(get_session)) -> list[ModelConfigInfo]:
    rows = (await session.execute(select(ModelConfig).order_by(ModelConfig.name))).scalars()
    return [_model_info(m) for m in rows]


@router.post("/models", response_model=ModelConfigInfo, dependencies=_WRITE)
async def create_model_config(
    body: ModelConfigRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ModelConfigInfo:
    exists = (
        await session.execute(select(ModelConfig).where(ModelConfig.name == body.name))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="model already registered")
    model = ModelConfig(**body.model_dump())
    session.add(model)
    await session.commit()
    await session.refresh(model)
    await _reload_registry(request)
    return _model_info(model)


@router.patch("/models/{model_id}", response_model=ModelConfigInfo, dependencies=_WRITE)
async def update_model_config(
    model_id: int,
    body: ModelConfigUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ModelConfigInfo:
    model = await session.get(ModelConfig, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")
    for field_name, value in body.model_dump(exclude_unset=True).items():
        setattr(model, field_name, value)
    await session.commit()
    await session.refresh(model)
    await _reload_registry(request)
    return _model_info(model)


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=_WRITE)
async def delete_model_config(
    model_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    model = await session.get(ModelConfig, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")
    await session.delete(model)
    await session.commit()
    await _reload_registry(request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- audit log ---------------------------------------------------------------


class AuditEntry(BaseModel):
    id: int
    trace_id: Optional[str]
    created_at: Optional[datetime]
    key_id: int
    tenant_id: str
    provider: str
    model: str
    prompt: str
    response: str


@router.get("/audit", response_model=list[AuditEntry])
async def list_audit(
    limit: int = 50, session: AsyncSession = Depends(get_session)
) -> list[AuditEntry]:
    """Recent captured prompt/response pairs (only populated when
    AUDIT_CAPTURE_CONTENT is enabled)."""
    limit = max(1, min(limit, 200))
    rows = (
        await session.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
    ).scalars().all()
    return [
        AuditEntry(
            id=r.id,
            trace_id=r.trace_id,
            created_at=r.created_at,
            key_id=r.key_id,
            tenant_id=r.tenant_id,
            provider=r.provider,
            model=r.model,
            prompt=r.prompt,
            response=r.response,
        )
        for r in rows
    ]
