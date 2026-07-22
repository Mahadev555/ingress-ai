"""Rough per-model prices for the cost ledger, in USD per 1M tokens.

These are approximate and easy to update; unknown models cost nothing rather
than guessing. A production deployment would likely load this from config.
"""

# model prefix -> (input_price_per_1m, output_price_per_1m)
PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
}


def _lookup(model: str) -> tuple[float, float]:
    # Longest matching prefix wins (handles versioned model names).
    best: tuple[float, float] = (0.0, 0.0)
    best_len = -1
    for prefix, price in PRICES.items():
        if model.startswith(prefix) and len(prefix) > best_len:
            best, best_len = price, len(prefix)
    return best


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    input_price, output_price = _lookup(model)
    cost = prompt_tokens / 1_000_000 * input_price + completion_tokens / 1_000_000 * output_price
    return round(cost, 6)
