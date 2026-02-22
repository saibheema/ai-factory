from collections import defaultdict
from time import perf_counter


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, float] = defaultdict(float)
        self._timers_sum: dict[str, float] = defaultdict(float)
        self._timers_count: dict[str, float] = defaultdict(float)

    def inc(self, name: str, value: float = 1.0) -> None:
        self._counters[name] += value

    def observe_ms(self, name: str, value_ms: float) -> None:
        self._timers_sum[name] += max(0.0, value_ms)
        self._timers_count[name] += 1.0

    def track_ms(self, name: str):
        registry = self

        class _Timer:
            def __enter__(self):
                self._start = perf_counter()
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                duration_ms = (perf_counter() - self._start) * 1000.0
                registry.observe_ms(name, duration_ms)

        return _Timer()

    def render_prometheus(self) -> str:
        lines: list[str] = []
        for key in sorted(self._counters.keys()):
            lines.append(f"# TYPE {key} counter")
            lines.append(f"{key} {self._counters[key]:.6f}")

        for key in sorted(self._timers_sum.keys()):
            sum_key = f"{key}_sum_ms"
            cnt_key = f"{key}_count"
            lines.append(f"# TYPE {sum_key} gauge")
            lines.append(f"{sum_key} {self._timers_sum[key]:.6f}")
            lines.append(f"# TYPE {cnt_key} counter")
            lines.append(f"{cnt_key} {self._timers_count[key]:.0f}")

        return "\n".join(lines) + "\n"
