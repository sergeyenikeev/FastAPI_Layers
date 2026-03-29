from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Settings — единая typed-конфигурация процесса. Все runtime и HTTP слои
    # читают окружение через эту модель, а не через прямые os.getenv вызовы.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="workflow-platform", alias="APP_NAME")
    app_env: Literal["dev", "test", "prod"] = Field(default="dev", alias="APP_ENV")
    debug: bool = Field(default=False, alias="DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8080, alias="PORT")

    database_url: str = Field(
        default="postgresql+asyncpg://workflow_user:replace-me@localhost:5432/workflow_db",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    kafka_bootstrap_servers: list[str] = Field(
        default_factory=lambda: ["localhost:9092"],
        alias="KAFKA_BOOTSTRAP_SERVERS",
    )
    kafka_client_id: str = Field(default="workflow-platform", alias="KAFKA_CLIENT_ID")
    kafka_security_protocol: str = Field(default="PLAINTEXT", alias="KAFKA_SECURITY_PROTOCOL")
    kafka_request_timeout_ms: int = Field(default=10000, alias="KAFKA_REQUEST_TIMEOUT_MS")
    kafka_enable_idempotence: bool = Field(default=True, alias="KAFKA_ENABLE_IDEMPOTENCE")

    api_keys: list[str] = Field(default_factory=list, alias="API_KEYS")
    jwt_secret: str = Field(default="replace-with-strong-secret", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")

    otel_exporter_otlp_endpoint: str | None = Field(
        default=None, alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    prometheus_enabled: bool = Field(default=True, alias="PROMETHEUS_ENABLED")

    default_alert_webhook: str | None = Field(default=None, alias="DEFAULT_ALERT_WEBHOOK")
    default_alert_email: str | None = Field(default=None, alias="DEFAULT_ALERT_EMAIL")
    alert_cooldown_seconds: int = Field(default=300, alias="ALERT_COOLDOWN_SECONDS")

    model_timeout_seconds: float = Field(default=30.0, alias="MODEL_TIMEOUT_SECONDS")
    model_probe_urls: list[str] = Field(default_factory=list, alias="MODEL_PROBE_URLS")

    cost_spike_zscore: float = Field(default=2.5, alias="COST_SPIKE_ZSCORE")
    latency_spike_zscore: float = Field(default=2.0, alias="LATENCY_SPIKE_ZSCORE")

    worker_role: str = Field(default="all", alias="WORKER_ROLE")
    heartbeat_ttl_seconds: int = Field(default=30, alias="HEARTBEAT_TTL_SECONDS")
    service_name: str = Field(default="workflow-api", alias="SERVICE_NAME")

    @field_validator("kafka_bootstrap_servers", "api_keys", "model_probe_urls", mode="before")
    @classmethod
    def _split_csv(cls, value: str | list[str] | None) -> list[str]:
        # Локальные env-файлы и Helm values могут поставлять списки как JSON-массив
        # или как CSV-строку. Валидатор нормализует оба варианта к одному типу.
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [item.strip() for item in value.split(",") if item.strip()]

    @field_validator("debug", "prometheus_enabled", "kafka_enable_idempotence", mode="before")
    @classmethod
    def _parse_bool(cls, value: object) -> bool:
        # Булевы env-значения часто приходят в разных формах из Docker/Helm/CI.
        # Валидатор делает их поведение предсказуемым на всех окружениях.
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "debug", "development"}:
            return True
        if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
            return False
        return bool(value)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Конфигурация кэшируется на процесс, чтобы все модули видели один и тот же
    # Settings instance и не парсили `.env` повторно на каждом импорте.
    return Settings()
