"""In-memory thread-safe metrics collector for QueryPilot operational telemetry."""

import math
import time
from threading import Lock
from typing import Any


class MetricsCollector:
    """Collects in-memory latency percentiles, request counts, and security events."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._start_time = time.time()

        # Route metrics: route -> status_code -> count
        self._route_counts: dict[str, dict[int, int]] = {}

        # Latencies in milliseconds: route -> list[float]
        self._route_latencies: dict[str, list[float]] = {}

        # LLM completion latencies: list[float]
        self._llm_latencies: list[float] = []

        # Agent step telemetry
        self._agent_runs_total: int = 0
        self._agent_steps_total: int = 0

        # Security & error counters
        self._validator_rejections_total: int = 0
        self._statement_timeouts_total: int = 0
        self._rate_limits_total: int = 0

    def record_request(self, route: str, status_code: int, latency_ms: float) -> None:
        """Record an incoming HTTP request completion."""
        with self._lock:
            # Normalize route patterns (strip trailing slashes)
            clean_route = route.rstrip("/") or "/"
            if clean_route not in self._route_counts:
                self._route_counts[clean_route] = {}
                self._route_latencies[clean_route] = []

            self._route_counts[clean_route][status_code] = (
                self._route_counts[clean_route].get(status_code, 0) + 1
            )
            # Store up to 10,000 latency measurements per route to prevent unbound memory
            if len(self._route_latencies[clean_route]) < 10000:
                self._route_latencies[clean_route].append(latency_ms)

            if status_code == 429:
                self._rate_limits_total += 1
            elif status_code == 504:
                self._statement_timeouts_total += 1

    def record_validator_rejection(self) -> None:
        """Increment count of AST validator security rejections."""
        with self._lock:
            self._validator_rejections_total += 1

    def record_llm_latency(self, latency_ms: float) -> None:
        """Record an LLM API completion latency."""
        with self._lock:
            if len(self._llm_latencies) < 10000:
                self._llm_latencies.append(latency_ms)

    def record_agent_run(self, step_count: int) -> None:
        """Record an agent run step count."""
        with self._lock:
            self._agent_runs_total += 1
            self._agent_steps_total += step_count

    def _calculate_percentile(self, values: list[float], percentile: float) -> float:
        """Calculate pth percentile from a list of numeric values."""
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        k = (len(sorted_vals) - 1) * (percentile / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return round(sorted_vals[int(k)], 2)
        d0 = sorted_vals[int(f)] * (c - k)
        d1 = sorted_vals[int(c)] * (k - f)
        return round(d0 + d1, 2)

    def get_summary(self) -> dict[str, Any]:
        """Generate a complete telemetry report."""
        with self._lock:
            uptime_seconds = round(time.time() - self._start_time, 1)

            route_summaries: dict[str, Any] = {}
            total_requests = 0

            for route, statuses in self._route_counts.items():
                latencies = self._route_latencies.get(route, [])
                route_reqs = sum(statuses.values())
                total_requests += route_reqs

                route_summaries[route] = {
                    "total_requests": route_reqs,
                    "status_counts": statuses,
                    "latency_p50_ms": self._calculate_percentile(latencies, 50),
                    "latency_p95_ms": self._calculate_percentile(latencies, 95),
                    "latency_avg_ms": round(sum(latencies) / len(latencies), 2)
                    if latencies
                    else 0.0,
                }

            avg_agent_steps = (
                round(self._agent_steps_total / self._agent_runs_total, 2)
                if self._agent_runs_total > 0
                else 0.0
            )

            return {
                "service": "querypilot-backend",
                "uptime_seconds": uptime_seconds,
                "memory_persistence_notice": "In-memory operational metrics. Counters and latency histograms reset upon server process restart.",
                "total_requests": total_requests,
                "routes": route_summaries,
                "security_events": {
                    "validator_rejections_total": self._validator_rejections_total,
                    "rate_limits_total": self._rate_limits_total,
                    "statement_timeouts_total": self._statement_timeouts_total,
                },
                "llm_telemetry": {
                    "completions_total": len(self._llm_latencies),
                    "latency_p50_ms": self._calculate_percentile(self._llm_latencies, 50),
                    "latency_p95_ms": self._calculate_percentile(self._llm_latencies, 95),
                },
                "agent_telemetry": {
                    "runs_total": self._agent_runs_total,
                    "steps_total": self._agent_steps_total,
                    "average_steps_per_run": avg_agent_steps,
                },
            }

    def reset(self) -> None:
        """Reset metrics (useful for isolated unit testing)."""
        with self._lock:
            self._route_counts.clear()
            self._route_latencies.clear()
            self._llm_latencies.clear()
            self._agent_runs_total = 0
            self._agent_steps_total = 0
            self._validator_rejections_total = 0
            self._statement_timeouts_total = 0
            self._rate_limits_total = 0


# Global singleton metrics collector
metrics_collector = MetricsCollector()
