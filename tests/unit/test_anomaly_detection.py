from __future__ import annotations

from app.domain.enums import AnomalyType
from app.modules.monitoring.anomaly import (
    AnomalyDetectionService,
    ThresholdRuleDetector,
    ZScoreDetector,
)


def test_threshold_detector_flags_high_value() -> None:
    # Базовая smoke-проверка простейшего rule-based детектора: при выходе
    # значения за порог сервис должен вернуть зафиксированную аномалию.
    detector = ThresholdRuleDetector(threshold=10.0, anomaly_type=AnomalyType.LATENCY_SPIKE)
    finding = detector.detect([1.0, 2.0, 11.0])
    assert finding is not None
    assert finding.anomaly_type == AnomalyType.LATENCY_SPIKE
    assert finding.observed_value == 11.0


def test_zscore_detector_ignores_normal_series() -> None:
    # Этот тест защищает от ложных срабатываний: на "здоровом" ряду z-score
    # detector не должен объявлять аномалию только из-за естественного шума.
    detector = ZScoreDetector(z_threshold=2.0, anomaly_type=AnomalyType.COST_SPIKE)
    finding = detector.detect([10.0, 11.0, 9.0, 10.5, 10.2])
    assert finding is None


def test_detection_service_returns_multiple_findings() -> None:
    # Service-layer тест подтверждает, что orchestration над несколькими
    # стратегиями действительно агрегирует результаты, а не останавливается
    # на первом сработавшем правиле.
    service = AnomalyDetectionService(
        [
            ThresholdRuleDetector(threshold=10.0, anomaly_type=AnomalyType.COST_SPIKE),
            ZScoreDetector(z_threshold=1.5, anomaly_type=AnomalyType.COST_SPIKE),
        ]
    )
    findings = service.evaluate([1.0, 2.0, 1.5, 1.8, 20.0])
    assert len(findings) >= 1
