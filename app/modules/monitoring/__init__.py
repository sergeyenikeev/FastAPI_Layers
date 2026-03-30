"""Monitoring and analytics module.

Содержит health checks, агрегирование метрик, anomaly detection и drift detection.
Модуль читает materialized данные и поток событий, но не управляет execution flow;
его задача — сделать поведение платформы наблюдаемым и операционно управляемым.
"""
