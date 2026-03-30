"""Database package.

Содержит persistence-слой платформы:
- базовый declarative registry;
- ORM-модели;
- session lifecycle;
- небольшие repository/helper-функции.

Пакет обслуживает как write-side, так и read-side, но не определяет бизнес-
правила сам по себе: он только предоставляет устойчивый доступ к PostgreSQL.
"""
