"""Prometheus metrics collector for QCE — no external library required."""
from __future__ import annotations
import threading


class QCEMetricsCollector:
    _instance: 'QCEMetricsCollector | None' = None
    _lock = threading.Lock()

    def __init__(self):
        self._cp_conf_sum   = 0.0
        self._cp_conf_count = 0
        self._cp_pool_sum   = 0
        self._cp_pool_count = 0
        self._amp_rounds_sum   = 0
        self._amp_rounds_count = 0
        self._gate: dict[str, int]    = {'direct': 0, 'sandbox': 0, 'hitl': 0, 'reject': 0}
        self._latency_sum: dict[str, float] = {}
        self._latency_count: dict[str, int] = {}
        self._reflection: dict[str, int]  = {'success': 0, 'partial': 0, 'failure': 0}
        self._interference: dict[str, int] = {'constructive': 0, 'destructive': 0}
        self._mu = threading.Lock()

    @classmethod
    def get(cls) -> 'QCEMetricsCollector':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def record_context_pack(self, confidence: float, pool_size: int, rounds: int) -> None:
        with self._mu:
            self._cp_conf_sum   += confidence
            self._cp_conf_count += 1
            self._cp_pool_sum   += pool_size
            self._cp_pool_count += 1
            self._amp_rounds_sum   += rounds
            self._amp_rounds_count += 1

    def record_gate(self, gate: str) -> None:
        with self._mu:
            self._gate[gate] = self._gate.get(gate, 0) + 1

    def record_engine_latency(self, engine: str, latency_ms: float) -> None:
        with self._mu:
            self._latency_sum[engine]   = self._latency_sum.get(engine, 0.0) + latency_ms
            self._latency_count[engine] = self._latency_count.get(engine, 0) + 1

    def record_reflection(self, outcome: str) -> None:
        with self._mu:
            self._reflection[outcome] = self._reflection.get(outcome, 0) + 1

    def record_interference(self, itype: str) -> None:
        with self._mu:
            self._interference[itype] = self._interference.get(itype, 0) + 1

    def prometheus_text(self) -> str:
        lines: list[str] = []

        def gauge(name: str, value: float | int, labels: str = '') -> None:
            lbl = '{' + labels + '}' if labels else ''
            lines.append(f'{name}{lbl} {value}')

        with self._mu:
            gauge('qce_context_pack_confidence_sum',   self._cp_conf_sum)
            gauge('qce_context_pack_confidence_count', self._cp_conf_count)
            gauge('qce_context_pack_pool_size_sum',    self._cp_pool_sum)
            gauge('qce_context_pack_pool_size_count',  self._cp_pool_count)
            gauge('qce_amplification_rounds_sum',      self._amp_rounds_sum)
            gauge('qce_amplification_rounds_count',    self._amp_rounds_count)

            for gate, val in self._gate.items():
                gauge('qce_gate_total', val, f'gate="{gate}"')

            for eng in self._latency_sum:
                gauge('qce_engine_latency_ms_sum',   self._latency_sum[eng],   f'engine="{eng}"')
                gauge('qce_engine_latency_ms_count', self._latency_count[eng], f'engine="{eng}"')

            for outcome, val in self._reflection.items():
                gauge('qce_reflection_total', val, f'outcome="{outcome}"')

            for itype, val in self._interference.items():
                gauge('qce_interference_total', val, f'type="{itype}"')

        return '\n'.join(lines) + '\n'
