from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.modules.orchestration.schemas import ModelInvocationResult

logger = get_logger(__name__)


class ModelGateway:
    # Gateway отделяет orchestration от конкретного способа вызова модели.
    # Благодаря этому workflow работает и с реальным внешним endpoint, и с
    # fallback-режимом локальной имитации, не меняя своего публичного контракта.
    def __init__(self) -> None:
        self.settings = get_settings()

    async def invoke(
        self,
        *,
        prompt: str,
        endpoint_url: str | None,
        provider: str | None,
        model_name: str | None,
        pricing: dict[str, Any] | None = None,
    ) -> ModelInvocationResult:
        # Все вызовы модели проходят через один gateway, чтобы расчет latency,
        # token usage и cost был единообразным для planner/reviewer и любых
        # будущих узлов графа.
        pricing = pricing or {}
        started = time.perf_counter()
        if endpoint_url:
            try:
                # Контракт intentionally минимальный: orchestration отправляет prompt
                # и model name, а остальная логика транспортного вызова скрыта здесь.
                async with httpx.AsyncClient(timeout=self.settings.model_timeout_seconds) as client:
                    response = await client.post(
                        endpoint_url.rstrip("/") + "/invoke",
                        json={"prompt": prompt, "model": model_name},
                    )
                    response.raise_for_status()
                    data = response.json()
                    content = str(data.get("content", ""))
            except Exception as exc:
                # Fallback делает workflow устойчивым для локальной разработки,
                # smoke-проверок и частичной деградации model endpoint-а.
                logger.warning("model.invoke.fallback", endpoint_url=endpoint_url, error=str(exc))
                content = self._fallback_response(prompt, model_name)
        else:
            content = self._fallback_response(prompt, model_name)

        # Даже fallback-ответ оформляется как полноценный ModelInvocationResult,
        # чтобы downstream telemetry, cost monitoring и step events имели единый формат.
        latency_ms = (time.perf_counter() - started) * 1000
        token_input = max(1, len(prompt.split()) * 2)
        token_output = max(1, len(content.split()) * 2)
        input_rate = float(pricing.get("input_per_1k", 0.001))
        output_rate = float(pricing.get("output_per_1k", 0.002))
        cost_usd = (token_input / 1000 * input_rate) + (token_output / 1000 * output_rate)
        return ModelInvocationResult(
            content=content,
            latency_ms=latency_ms,
            token_input=token_input,
            token_output=token_output,
            cost_usd=cost_usd,
            model_name=model_name or "mock-model",
            provider=provider or "mock",
        )

    def _fallback_response(self, prompt: str, model_name: str | None) -> str:
        # Fallback deliberately детерминирован и короток: он нужен не как "умная"
        # модель, а как безопасный заменитель для мест, где важен сам workflow flow.
        short_prompt = prompt[:240]
        return f"[{model_name or 'mock-model'}] synthesized response for: {short_prompt}"
