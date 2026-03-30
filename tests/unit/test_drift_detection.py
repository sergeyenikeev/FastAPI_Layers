from __future__ import annotations

from app.modules.monitoring.drift import (
    DriftDetectionService,
    JensenShannonDetector,
    PSIDetector,
    jensen_shannon_divergence,
    population_stability_index,
)


def test_population_stability_index_detects_distribution_shift() -> None:
    # PSI используется как простой production-friendly индикатор сдвига
    # распределения. Тест защищает ожидаемую чувствительность метрики на
    # заведомо разных выборках.
    baseline = [1.0] * 20 + [2.0] * 20
    current = [8.0] * 20 + [9.0] * 20
    assert population_stability_index(baseline, current) > 0.2


def test_jensen_shannon_divergence_is_zero_for_identical_inputs() -> None:
    # У идентичных распределений дивергенция должна быть нулевой; это важный
    # sanity-check для численной стабильности реализации.
    values = [0.25, 0.25, 0.25, 0.25]
    assert jensen_shannon_divergence(values, values) == 0.0


def test_drift_detection_service_finds_drift() -> None:
    # Комбинированный service-layer тест подтверждает, что orchestration над
    # несколькими drift detector-ами возвращает факты drift при сильном сдвиге.
    service = DriftDetectionService(
        [PSIDetector(threshold=0.1), JensenShannonDetector(threshold=0.05)]
    )
    findings = service.evaluate([1.0] * 20 + [2.0] * 20, [5.0] * 20 + [6.0] * 20)
    assert findings
