from __future__ import annotations

import math
from typing import Protocol

from pydantic import BaseModel

from app.domain.enums import AlertSeverity, DriftType


class DriftFinding(BaseModel):
    drift_type: str
    severity: str
    metric_name: str
    score: float
    threshold: float
    reason: str


class DriftDetector(Protocol):
    def detect(self, baseline: list[float], current: list[float]) -> DriftFinding | None: ...


def population_stability_index(
    baseline: list[float], current: list[float], bins: int = 10
) -> float:
    if not baseline or not current:
        return 0.0
    min_value = min(min(baseline), min(current))
    max_value = max(max(baseline), max(current))
    if min_value == max_value:
        return 0.0
    step = (max_value - min_value) / bins
    psi = 0.0
    for index in range(bins):
        lower = min_value + (step * index)
        upper = max_value if index == bins - 1 else lower + step
        baseline_count = sum(1 for value in baseline if lower <= value <= upper)
        current_count = sum(1 for value in current if lower <= value <= upper)
        baseline_pct = max(baseline_count / len(baseline), 1e-6)
        current_pct = max(current_count / len(current), 1e-6)
        psi += (current_pct - baseline_pct) * math.log(current_pct / baseline_pct)
    return psi


def kl_divergence(p: list[float], q: list[float]) -> float:
    total = 0.0
    for p_value, q_value in zip(p, q, strict=False):
        p_safe = max(p_value, 1e-9)
        q_safe = max(q_value, 1e-9)
        total += p_safe * math.log(p_safe / q_safe)
    return total


def jensen_shannon_divergence(baseline: list[float], current: list[float]) -> float:
    if not baseline or not current:
        return 0.0
    size = min(len(baseline), len(current))
    p = baseline[:size]
    q = current[:size]
    p_sum = sum(p) or 1.0
    q_sum = sum(q) or 1.0
    p_norm = [value / p_sum for value in p]
    q_norm = [value / q_sum for value in q]
    midpoint = [(p_value + q_value) / 2 for p_value, q_value in zip(p_norm, q_norm, strict=False)]
    return 0.5 * kl_divergence(p_norm, midpoint) + 0.5 * kl_divergence(q_norm, midpoint)


class PSIDetector:
    def __init__(self, threshold: float = 0.2, drift_type: str = DriftType.DATA_DRIFT) -> None:
        self.threshold = threshold
        self.drift_type = drift_type

    def detect(self, baseline: list[float], current: list[float]) -> DriftFinding | None:
        score = population_stability_index(baseline, current)
        if score >= self.threshold:
            severity = (
                AlertSeverity.CRITICAL if score >= self.threshold * 1.5 else AlertSeverity.WARNING
            )
            return DriftFinding(
                drift_type=self.drift_type,
                severity=severity,
                metric_name="psi",
                score=score,
                threshold=self.threshold,
                reason="psi_threshold_exceeded",
            )
        return None


class JensenShannonDetector:
    def __init__(self, threshold: float = 0.1, drift_type: str = DriftType.OUTPUT_DRIFT) -> None:
        self.threshold = threshold
        self.drift_type = drift_type

    def detect(self, baseline: list[float], current: list[float]) -> DriftFinding | None:
        score = jensen_shannon_divergence(baseline, current)
        if score >= self.threshold:
            severity = (
                AlertSeverity.CRITICAL if score >= self.threshold * 2 else AlertSeverity.WARNING
            )
            return DriftFinding(
                drift_type=self.drift_type,
                severity=severity,
                metric_name="jensen_shannon",
                score=score,
                threshold=self.threshold,
                reason="js_threshold_exceeded",
            )
        return None


class DriftDetectionService:
    def __init__(self, detectors: list[DriftDetector]) -> None:
        self.detectors = detectors

    def evaluate(self, baseline: list[float], current: list[float]) -> list[DriftFinding]:
        findings: list[DriftFinding] = []
        for detector in self.detectors:
            finding = detector.detect(baseline, current)
            if finding:
                findings.append(finding)
        return findings


def build_default_drift_detectors() -> list[DriftDetector]:
    return [
        PSIDetector(threshold=0.2, drift_type=DriftType.DATA_DRIFT),
        JensenShannonDetector(threshold=0.1, drift_type=DriftType.OUTPUT_DRIFT),
        JensenShannonDetector(threshold=0.15, drift_type=DriftType.EMBEDDING_DRIFT),
    ]
