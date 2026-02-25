from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Dict


class QAMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self.total_requests = 0
        self.total_fallback = 0
        self.total_verify_failed = 0
        self.total_latency_ms = 0.0
        self.route_counter: Dict[str, int] = defaultdict(int)

    def record_request(self, route: str, latency_ms: float) -> None:
        with self._lock:
            self.total_requests += 1
            self.total_latency_ms += latency_ms
            self.route_counter[route] += 1

    def record_fallback(self) -> None:
        with self._lock:
            self.total_fallback += 1

    def record_verify_failed(self) -> None:
        with self._lock:
            self.total_verify_failed += 1

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            avg_latency = self.total_latency_ms / self.total_requests if self.total_requests else 0.0
            fallback_ratio = self.total_fallback / self.total_requests if self.total_requests else 0.0
            return {
                "total_requests": self.total_requests,
                "total_fallback": self.total_fallback,
                "total_verify_failed": self.total_verify_failed,
                "avg_latency_ms": round(avg_latency, 2),
                "fallback_ratio": round(fallback_ratio, 4),
                "route_counter": dict(self.route_counter),
            }


qa_metrics = QAMetrics()
