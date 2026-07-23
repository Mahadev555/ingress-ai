from app.core.concurrency import ConcurrencyLimiter


def test_concurrency_limiter_blocks_over_limit():
    limiter = ConcurrencyLimiter()
    assert limiter.acquire(1, 2) is True
    assert limiter.acquire(1, 2) is True
    assert limiter.acquire(1, 2) is False  # third exceeds the cap of 2
    limiter.release(1)
    assert limiter.acquire(1, 2) is True  # a slot freed up


def test_concurrency_limiter_none_means_unlimited():
    limiter = ConcurrencyLimiter()
    for _ in range(100):
        assert limiter.acquire(7, None) is True


def test_concurrency_limiter_is_per_key():
    limiter = ConcurrencyLimiter()
    assert limiter.acquire(1, 1) is True
    assert limiter.acquire(2, 1) is True  # different key, own budget
    assert limiter.acquire(1, 1) is False
