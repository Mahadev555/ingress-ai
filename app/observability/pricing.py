"""Per-model prices for the cost ledger, in USD per 1M tokens.

There is deliberately no hardcoded price table: baked-in prices go stale and
never cover the models you actually add. Prices come only from the DB model
registry — set a model's input/output price on the Models page if you want cost
estimates for it. Models with no price simply cost $0 (token accounting still
works), and cost tracking can be turned off entirely via COST_TRACKING_ENABLED.
"""

# Exact-name prices loaded from the DB model registry (USD per 1M tokens).
_OVERRIDES: dict[str, tuple[float, float]] = {}


def set_overrides(overrides: dict[str, tuple[float, float]]) -> None:
    """Replace the DB-sourced prices (called by the model registry on reload)."""
    global _OVERRIDES
    _OVERRIDES = dict(overrides)


def price_for(model: str) -> tuple[float, float]:
    """Price (input, output) per 1M tokens for a model; (0, 0) if none is set."""
    return _OVERRIDES.get(model, (0.0, 0.0))


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    input_price, output_price = price_for(model)
    cost = prompt_tokens / 1_000_000 * input_price + completion_tokens / 1_000_000 * output_price
    return round(cost, 6)
