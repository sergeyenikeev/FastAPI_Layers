from __future__ import annotations

from collections import deque
from statistics import mean, pstdev
from typing import Protocol

from pydantic import BaseModel

from app.domain.enums import AlertSeverity, AnomalyType


class AnomalyFinding(BaseModel):
    # Finding — нормализованный результат detector-а, из которого потом строится
    # anomaly event и materialized anomaly report.
    anomaly_type: str
    severity: str
    score: float
    baseline_value: float
    observed_value: float
    reason: str


class AnomalyDetector(Protocol):
    def detect(self, values: list[float]) -> AnomalyFinding | None: ...


class ThresholdRuleDetector:
    # Threshold detector нужен для грубых, но прозрачных guard rails, где
    # порог заранее известен и должен срабатывать без статистического baseline.
    def __init__(self, threshold: float, anomaly_type: str = AnomalyType.LATENCY_SPIKE) -> None:
        self.threshold = threshold
        self.anomaly_type = anomaly_type

    def detect(self, values: list[float]) -> AnomalyFinding | None:
        if not values:
            return None
        observed = values[-1]
        if observed > self.threshold:
            return AnomalyFinding(
                anomaly_type=self.anomaly_type,
                severity=AlertSeverity.CRITICAL,
                score=observed / self.threshold,
                baseline_value=self.threshold,
                observed_value=observed,
                reason="threshold_exceeded",
            )
        return None


class RollingStdDetector:
    # RollingStdDetector ловит локальные всплески относительно недавнего окна,
    # когда абсолютный threshold не подходит, но важна краткосрочная динамика.
    def __init__(self, window_size: int = 10, std_multiplier: float = 2.0) -> None:
        self.window_size = window_size
        self.std_multiplier = std_multiplier

    def detect(self, values: list[float]) -> AnomalyFinding | None:
        if len(values) < max(3, self.window_size):
            return None
        window = deque(values[-self.window_size :], maxlen=self.window_size)
        observed = window[-1]
        baseline = list(window)[:-1]
        baseline_mean = mean(baseline)
        baseline_std = pstdev(baseline) or 1e-6
        limit = baseline_mean + (baseline_std * self.std_multiplier)
        if observed > limit:
            return AnomalyFinding(
                anomaly_type=AnomalyType.ERROR_SPIKE,
                severity=AlertSeverity.WARNING,
                score=(observed - baseline_mean) / baseline_std,
                baseline_value=baseline_mean,
                observed_value=observed,
                reason="rolling_std_exceeded",
            )
        return None


class ZScoreDetector:
    # Z-score detector — более общий статистический механизм, который хорошо
    # работает для latency/cost spikes без жестко заданного абсолютного порога.
    def __init__(self, z_threshold: float, anomaly_type: str) -> None:
        self.z_threshold = z_threshold
        self.anomaly_type = anomaly_type

    def detect(self, values: list[float]) -> AnomalyFinding | None:
        if len(values) < 5:
            return None
        observed = values[-1]
        baseline = values[:-1]
        baseline_mean = mean(baseline)
        baseline_std = pstdev(baseline) or 1e-6
        z_score = abs((observed - baseline_mean) / baseline_std)
        if z_score >= self.z_threshold:
            severity = (
                AlertSeverity.CRITICAL
                if z_score >= self.z_threshold * 1.5
                else AlertSeverity.WARNING
            )
            return AnomalyFinding(
                anomaly_type=self.anomaly_type,
                severity=severity,
                score=z_score,
                baseline_value=baseline_mean,
                observed_value=observed,
                reason="zscore_exceeded",
            )
        return None


class AnomalyDetectionService:
    # Сервис делает anomaly detection pluggable: pipeline не знает, какие именно
    # detectors используются, и может расширяться добавлением новых стратегий.
    def __init__(self, detectors: list[AnomalyDetector]) -> None:
        self.detectors = detectors

    def evaluate(self, values: list[float]) -> list[AnomalyFinding]:
        findings: list[AnomalyFinding] = []
        for detector in self.detectors:
            finding = detector.detect(values)
            if finding:
                findings.append(finding)
        return findings


def build_default_anomaly_detectors(
    latency_zscore: float, cost_zscore: float
) -> list[AnomalyDetector]:
    # Набор по умолчанию сочетает rule-based и статистические подходы, чтобы
    # платформа ловила как грубые threshold violations, так и мягкие выбросы.
    return [
        ThresholdRuleDetector(threshold=5000.0, anomaly_type=AnomalyType.LATENCY_SPIKE),
        RollingStdDetector(window_size=10, std_multiplier=2.0),
        ZScoreDetector(z_threshold=latency_zscore, anomaly_type=AnomalyType.LATENCY_SPIKE),
        ZScoreDetector(z_threshold=cost_zscore, anomaly_type=AnomalyType.COST_SPIKE),
    ]
