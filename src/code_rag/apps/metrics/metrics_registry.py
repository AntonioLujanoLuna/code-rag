from __future__ import annotations

import math
import re
from collections import defaultdict
from threading import RLock
from typing import Any

from code_rag.apps.metrics.timing_stats import DEFAULT_BUCKETS, TimingStats


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: defaultdict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
        self._timings: defaultdict[tuple[str, tuple[tuple[str, str], ...]], TimingStats] = (
            defaultdict(TimingStats)
        )
        self._lock = RLock()

    def increment(self, name: str, value: int = 1, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._counters[(name, self._labels(labels))] += value

    def observe(self, name: str, seconds: float, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._timings[(name, self._labels(labels))].observe(seconds)

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            return {
                "counters": {
                    self._metric_key(name, labels): value
                    for (name, labels), value in self._counters.items()
                },
                "timings": {
                    self._metric_key(name, labels): timing.snapshot()
                    for (name, labels), timing in self._timings.items()
                },
            }

    def prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (name, labels), value in sorted(self._counters.items()):
                metric = _sanitize_metric_name(name)
                lines.append(f"# TYPE {metric} counter")
                lines.append(f"{metric}{self._format_labels(labels)} {value}")
            for (name, labels), timing in sorted(self._timings.items()):
                metric = _sanitize_metric_name(name)
                lines.append(f"# TYPE {metric} histogram")
                for bucket in DEFAULT_BUCKETS:
                    bucket_labels = (*labels, ("le", str(bucket)))
                    value = timing.buckets.get(bucket, 0) if timing.buckets else 0
                    lines.append(f"{metric}_bucket{self._format_labels(bucket_labels)} {value}")
                inf_labels = (*labels, ("le", "+Inf"))
                lines.append(f"{metric}_bucket{self._format_labels(inf_labels)} {timing.count}")
                lines.append(f"{metric}_count{self._format_labels(labels)} {timing.count}")
                lines.append(
                    f"{metric}_sum{self._format_labels(labels)} "
                    f"{_prometheus_float(timing.total_seconds)}"
                )
        return "\n".join(lines) + "\n"

    def _labels(self, labels: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
        if not labels:
            return ()
        return tuple(sorted((str(key), str(value)) for key, value in labels.items()))

    def _metric_key(self, name: str, labels: tuple[tuple[str, str], ...]) -> str:
        if not labels:
            return name
        label_text = ",".join(f"{key}={value}" for key, value in labels)
        return f"{name}{{{label_text}}}"

    def _format_labels(self, labels: tuple[tuple[str, str], ...]) -> str:
        if not labels:
            return ""
        escaped = ",".join(f'{key}="{_escape_label(value)}"' for key, value in labels)
        return "{" + escaped + "}"


def _sanitize_metric_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_:]", "_", name)


def _escape_label(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _prometheus_float(value: float) -> str:
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    if math.isnan(value):
        return "NaN"
    return repr(value)
