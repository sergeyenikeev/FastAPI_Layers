from __future__ import annotations

from app.domain.enums import AnomalyType
from app.modules.monitoring.anomaly import (
    AnomalyDetectionService,
    ThresholdRuleDetector,
    ZScoreDetector,
)


def test_threshold_detector_flags_high_value() -> None:
    detector = ThresholdRuleDetector(threshold=10.0, anomaly_type=AnomalyType.LATENCY_SPIKE)
    finding = detector.detect([1.0, 2.0, 11.0])
    assert finding is not None
    assert finding.anomaly_type == AnomalyType.LATENCY_SPIKE
    assert finding.observed_value == 11.0


def test_zscore_detector_ignores_normal_series() -> None:
    detector = ZScoreDetector(z_threshold=2.0, anomaly_type=AnomalyType.COST_SPIKE)
    finding = detector.detect([10.0, 11.0, 9.0, 10.5, 10.2])
    assert finding is None


def test_detection_service_returns_multiple_findings() -> None:
    service = AnomalyDetectionService(
        [
            ThresholdRuleDetector(threshold=10.0, anomaly_type=AnomalyType.COST_SPIKE),
            ZScoreDetector(z_threshold=1.5, anomaly_type=AnomalyType.COST_SPIKE),
        ]
    )
    findings = service.evaluate([1.0, 2.0, 1.5, 1.8, 20.0])
    assert len(findings) >= 1
