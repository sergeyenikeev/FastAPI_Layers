"""Orchestration module.

Здесь находится runtime-логика запуска execution run:
- HTTP-вход для старта выполнения;
- query-layer для чтения history запусков;
- LangGraph workflow;
- model gateway;
- command service, связывающий deployment, execution и event emission.
"""
