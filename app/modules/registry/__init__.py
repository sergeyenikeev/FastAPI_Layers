"""Registry module.

Хранит catalog/configuration bounded context:
- агенты и их версии;
- графы выполнения;
- модели и их версии;
- deployment-конфигурации;
- инструменты и окружения.

Именно этот модуль отвечает за command-side CRUD и публикацию событий,
из которых затем строятся read-model проекции для API.
"""
