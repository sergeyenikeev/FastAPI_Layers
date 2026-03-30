"""Domain types and schemas.

Содержит общие доменные перечисления, event envelope и DTO/response-схемы,
которые переиспользуются несколькими bounded context-ами.

Это не "богатая доменная модель" в DDD-смысле, а скорее shared contract layer,
нужный для согласованности API, событий Kafka и materialized read-model.
"""
