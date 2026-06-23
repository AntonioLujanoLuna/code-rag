from __future__ import annotations

from collections import defaultdict
from threading import RLock

from code_rag.apps.metrics.timing_stats import TimingStats


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: defaultdict[str, int] = defaultdict(int)
        self._timings: defaultdict[str, TimingStats] = defaultdict(TimingStats)
        self._lock = RLock()

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def observe(self, name: str, seconds: float) -> None:
        with self._lock:
            self._timings[name].observe(seconds)

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "timings": {name: timing.snapshot() for name, timing in self._timings.items()},
            }
