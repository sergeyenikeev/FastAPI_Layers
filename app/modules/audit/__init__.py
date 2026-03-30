"""Audit module.

Отвечает за audit trail платформы:
- фиксацию значимых событий и действий;
- хранение correlation_id и trace_id рядом с событием;
- отдачу audit-истории через read-side API.

Это отдельный bounded context, потому что аудит важен не только для debugging,
но и для compliance, расследований и анализа изменений в продакшене.
"""
