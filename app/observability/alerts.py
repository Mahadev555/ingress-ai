"""Budget alerts.

Fire a Slack-compatible webhook when a key or team crosses a budget threshold —
a soft warning at ``alert_soft_threshold`` (e.g. 80%) and a hard alert at 100%.
This is what turns the usage ledger from a passive record into something ops
actually reacts to.

Best-effort and de-duplicated per (scope, id, window, level) so a busy key does
not spam the channel: each level fires at most once per budget window, in-process.
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger("ingress.alerts")

# Remembers which (scope, id, window, level) alerts have already fired.
_fired: set[tuple[str, int, str, str]] = set()


def reset() -> None:
    """Clear the de-dupe memory (used by tests)."""
    _fired.clear()


def _crossed(used: float, budget: Optional[float], soft: float) -> Optional[str]:
    """Return "hard", "soft", or None for how far `used` is into `budget`."""
    if not budget or budget <= 0:
        return None
    ratio = used / budget
    if ratio >= 1.0:
        return "hard"
    if ratio >= soft:
        return "soft"
    return None


async def _post(client: httpx.AsyncClient, url: str, text: str) -> None:
    try:
        await client.post(url, json={"text": text}, timeout=5.0)
    except Exception:  # pragma: no cover - alerting must never break a request
        logger.exception("failed to post budget alert")


async def _maybe_fire(
    client: httpx.AsyncClient,
    url: str,
    soft: float,
    scope: str,  # "key" | "team"
    scope_id: int,
    label: str,
    window: str,
    token_used: int,
    token_budget: Optional[int],
    cost_used: float,
    cost_budget: Optional[float],
) -> None:
    for kind, used, budget, unit in (
        ("token", token_used, token_budget, "tokens"),
        ("cost", cost_used, cost_budget, "USD"),
    ):
        level = _crossed(float(used), float(budget) if budget else None, soft)
        if level is None:
            continue
        marker = (scope, scope_id, window, f"{kind}:{level}")
        if marker in _fired:
            continue
        _fired.add(marker)
        pct = round(100 * used / budget) if budget else 0
        emoji = "🚨" if level == "hard" else "⚠️"
        await _post(
            client,
            url,
            f"{emoji} {scope} {label} at {pct}% of its {kind} budget "
            f"({used} of {budget} {unit}, window={window}).",
        )


async def check_key_budget(client: httpx.AsyncClient, url: str, soft: float, key) -> None:
    """Alert on a resolved KeyContext's key-level (and team-level) budgets."""
    if not url:
        return
    await _maybe_fire(
        client, url, soft, "key", key.key_id, key.name or f"#{key.key_id}",
        key.budget_period, key.tokens_used, key.token_budget,
        key.cost_used, key.cost_budget_usd,
    )
    if key.team_id is not None:
        await _maybe_fire(
            client, url, soft, "team", key.team_id, f"#{key.team_id}",
            key.team_budget_period, key.team_tokens_used, key.team_token_budget,
            key.team_cost_used, key.team_cost_budget_usd,
        )
