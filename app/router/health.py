import time
from dataclasses import dataclass


@dataclass
class _ProviderState:
    failures: int = 0
    opened_at: float | None = None


class CircuitBreaker:
    """Per-provider circuit breaker.

    After ``fail_threshold`` consecutive failures a provider's circuit opens and
    requests skip it until ``reset_timeout`` elapses, at which point it half-opens
    (one trial allowed). A success closes it again.

    State is per-process; that is enough to stop hammering a down provider on
    each replica. A shared (Redis) breaker is a clean later addition.
    """

    def __init__(self, fail_threshold: int = 5, reset_timeout: float = 30.0) -> None:
        self.fail_threshold = fail_threshold
        self.reset_timeout = reset_timeout
        self._states: dict[str, _ProviderState] = {}

    def is_open(self, provider: str) -> bool:
        state = self._states.get(provider)
        if state is None or state.opened_at is None:
            return False
        if time.monotonic() - state.opened_at >= self.reset_timeout:
            # Half-open: allow the next request through as a trial.
            state.opened_at = None
            state.failures = 0
            return False
        return True

    def record_success(self, provider: str) -> None:
        self._states[provider] = _ProviderState()

    def record_failure(self, provider: str) -> None:
        state = self._states.setdefault(provider, _ProviderState())
        state.failures += 1
        if state.failures >= self.fail_threshold:
            state.opened_at = time.monotonic()
