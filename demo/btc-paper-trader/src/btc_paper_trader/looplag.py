"""Event-loop lag monitor: a 50 ms heartbeat that records how late each wake-up was."""

from __future__ import annotations

import asyncio
import time
from collections import deque

INTERVAL_S = 0.05
WINDOW_S = 60.0


class LoopLagMonitor:
    def __init__(self) -> None:
        self._samples: deque[tuple[float, float]] = deque()  # (monotonic time, lag ms)

    async def run(self) -> None:
        while True:
            start = time.monotonic()
            await asyncio.sleep(INTERVAL_S)
            now = time.monotonic()
            self._samples.append((now, max(0.0, (now - start - INTERVAL_S) * 1000)))
            cutoff = now - WINDOW_S
            while self._samples and self._samples[0][0] < cutoff:
                self._samples.popleft()

    def snapshot(self) -> dict[str, float]:
        lags = sorted(lag for _, lag in self._samples)
        if not lags:
            return {"max": 0.0, "p99": 0.0}
        p99 = lags[min(len(lags) - 1, int(len(lags) * 0.99))]
        return {"max": round(lags[-1], 2), "p99": round(p99, 2)}
