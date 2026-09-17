"""Límites en memoria. Válidos para un solo proceso: con varios workers hace falta un store compartido."""

import time
from collections import Counter
from collections.abc import Callable


class TokenBucket:
    def __init__(self, capacity: int, refill_per_second: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._capacity = capacity
        self._refill = refill_per_second
        self._clock = clock
        self._tokens = float(capacity)
        self._updated = clock()

    def consume(self) -> bool:
        now = self._clock()
        self._tokens = min(self._capacity, self._tokens + (now - self._updated) * self._refill)
        self._updated = now
        if self._tokens < 1:
            return False
        self._tokens -= 1
        return True


class ConnectionLimiter:
    """Conexiones simultáneas por IP. Sin await entre chequeo e incremento: seguro en un event loop."""

    def __init__(self, max_per_ip: int) -> None:
        self._max = max_per_ip
        self._active: Counter[str] = Counter()

    def acquire(self, ip: str) -> bool:
        if self._active[ip] >= self._max:
            return False
        self._active[ip] += 1
        return True

    def release(self, ip: str) -> None:
        self._active[ip] -= 1
        if self._active[ip] <= 0:
            del self._active[ip]
