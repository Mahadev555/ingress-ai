from dataclasses import dataclass
from typing import Optional, Union

import httpx

from app.resilience.retry import ClientError, RetryConfig, TransientError, with_retries
from app.router.health import CircuitBreaker
from app.router.selector import Candidate
from app.schemas.unified import ChatCompletionRequest


@dataclass
class Success:
    candidate: Candidate
    response: httpx.Response


@dataclass
class Failure:
    status_code: int
    message: str
    body: Optional[dict] = None
    provider: Optional[str] = None


Outcome = Union[Success, Failure]


async def execute_with_fallback(
    candidates: list[Candidate],
    payload: ChatCompletionRequest,
    client: httpx.AsyncClient,
    breaker: CircuitBreaker,
    retry_config: RetryConfig,
) -> Outcome:
    """Try each candidate in order until one succeeds.

    Per candidate: retry transient failures; on exhaustion mark the provider
    unhealthy and move on. A non-retryable 4xx is relayed immediately (no
    failover). Open circuits are skipped.
    """
    failure = Failure(503, "no providers available")

    for candidate in candidates:
        if breaker.is_open(candidate.provider):
            failure = Failure(
                503, f"provider {candidate.provider} temporarily unavailable",
                provider=candidate.provider,
            )
            continue

        attempt_payload = payload.model_copy(update={"model": candidate.model})

        try:
            response = await with_retries(
                lambda c=candidate, p=attempt_payload: _attempt(c, p, client),
                retry_config,
            )
        except ClientError as error:
            return Failure(
                error.status_code, "upstream rejected the request",
                error.body, provider=candidate.provider,
            )
        except TransientError as error:
            breaker.record_failure(candidate.provider)
            failure = Failure(
                error.status_code, error.message, error.body, provider=candidate.provider
            )
            continue

        breaker.record_success(candidate.provider)
        return Success(candidate, response)

    return failure


async def _attempt(
    candidate: Candidate,
    payload: ChatCompletionRequest,
    client: httpx.AsyncClient,
) -> httpx.Response:
    native = candidate.adapter.build_request(payload, candidate.creds)
    try:
        response = await client.request(
            native.method, native.url, headers=native.headers, json=native.json
        )
    except httpx.RequestError as exc:
        raise TransientError(502, f"upstream request failed: {exc}") from exc

    if response.status_code >= 500 or response.status_code == 429:
        raise TransientError(response.status_code, "upstream error", _safe_json(response))
    if response.status_code >= 400:
        raise ClientError(response.status_code, _safe_json(response))

    return response


def _safe_json(response: httpx.Response) -> Optional[dict]:
    try:
        return response.json()
    except ValueError:
        return None
