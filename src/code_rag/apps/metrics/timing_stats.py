from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TimingStats:
    count: int = 0
    total_seconds: float = 0.0
    min_seconds: float | None = None
    max_seconds: float | None = None

    def observe(self, value: float) -> None:
        self.count += 1
        self.total_seconds += value
        self.min_seconds = value if self.min_seconds is None else min(self.min_seconds, value)
        self.max_seconds = value if self.max_seconds is None else max(self.max_seconds, value)

    def snapshot(self) -> dict[str, float | int | None]:
        average = self.total_seconds / self.count if self.count else 0.0
        return {
            "count": self.count,
            "total_seconds": self.total_seconds,
            "avg_seconds": average,
            "min_seconds": self.min_seconds,
            "max_seconds": self.max_seconds,
        }
