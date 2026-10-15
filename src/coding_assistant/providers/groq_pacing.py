"""Conservative in-process request pacing; this cannot increase account quotas."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
import math
import time

from coding_assistant.contracts import Payload


class RequestPacer:
    """Reserve estimated input + maximum output against a rolling minute window.

    Share one instance per model across an evaluation. Other programs and daily
    usage are unknown; Groq's 429 response remains authoritative. Reservations
    are kept even on failed requests, deliberately avoiding optimistic refunds.
    """

    def __init__(self, tokens_per_minute: int = 7000, *, min_interval: float = 2.1,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        if isinstance(tokens_per_minute, bool) or tokens_per_minute < 3000:
            raise ValueError("tokens_per_minute must be at least 3000")
        if not math.isfinite(min_interval) or min_interval < 0:
            raise ValueError("min_interval must be nonnegative and finite")
        self.tokens_per_minute = tokens_per_minute
        self.min_interval = min_interval
        self._clock, self._sleep = clock, sleep
        self._reservations: deque[tuple[float, int]] = deque()
        self._last: float | None = None
        self._lock = asyncio.Lock()

    async def reserve(self, estimated_tokens: int) -> AsyncIterator[Payload]:
        if not 0 < estimated_tokens <= self.tokens_per_minute:
            raise ValueError("Request estimate exceeds the pacing allowance")
        async with self._lock:
            while True:
                now = self._clock()
                while self._reservations and now - self._reservations[0][0] >= 60:
                    self._reservations.popleft()
                delay = max(0.0, self.min_interval - (now - self._last)) if self._last is not None else 0.0
                if sum(tokens for _, tokens in self._reservations) + estimated_tokens > self.tokens_per_minute:
                    delay = max(delay, 60 - (now - self._reservations[0][0]))
                if delay <= 0:
                    self._reservations.append((now, estimated_tokens))
                    self._last = now
                    return
                step = min(5.0, delay)
                yield {"type": "status", "content": f"Groq pacing: about {math.ceil(delay)}s remaining",
                       "wait_seconds": step}
                await self._sleep(step)
