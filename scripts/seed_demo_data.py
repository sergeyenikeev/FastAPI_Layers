from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import (
    Agent,
    AgentVersion,
    Deployment,
    Environment,
    GraphDefinition,
    ModelEndpoint,
    ModelVersion,
)

# Скрипт идемпотентно наполняет локальный registry/read-side demo-сущностями.
# Он использует публичный API для write-side команд и БД только там, где нужно
# дождаться materialized version/entity id для последующих связей deployment-а.
ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_TIMEOUT_SECONDS = 90


@dataclass(frozen=True)
class GraphSeed:
    # Небольшие typed dataclass-ы делают seed-набор явно структурированным и
    # читаемым, вместо разрозненных невалидируемых dict-констант.
    name: str
    description: str
    entrypoint: str
    version: str
    definition: dict[str, Any]


@dataclass(frozen=True)
class ModelSeed:
    name: str
    provider: str
    base_url: str
    auth_type: str
    version: str
    model_name: str
    tokenizer_name: str | None
    context_window: int
    pricing: dict[str, Any]
    capabilities: dict[str, Any]


@dataclass(frozen=True)
class EnvironmentSeed:
    name: str
    description: str
    labels: dict[str, Any]


@dataclass(frozen=True)
class AgentSeed:
    name: str
    description: str
    owner: str
    version: str
    graph_name: str
    tags: dict[str, Any]
    runtime_config: dict[str, Any]


@dataclass(frozen=True)
class DeploymentSeed:
    seed_key: str
    agent_name: str
    agent_version: str
    model_name: str
    model_version: str
    environment_name: str
    replica_count: int
    configuration: dict[str, Any]


DEMO_GRAPHS = [
    GraphSeed(
        name="billing-operations-graph",
        description="Базовый граф обработки инцидентов и деградаций платежного контура.",
        version="v1",
        entrypoint="planner",
        definition={
            "nodes": ["planner", "tool_runner", "reviewer"],
            "edges": [["planner", "tool_runner"], ["tool_runner", "reviewer"]],
            "purpose": "incident-triage",
        },
    ),
    GraphSeed(
        name="validator-enabled-graph",
        description="Граф с дополнительной веткой validator для рискованных изменений.",
        version="v1",
        entrypoint="planner",
        definition={
            "nodes": ["planner", "tool_runner", "validator", "reviewer"],
            "edges": [
                ["planner", "tool_runner"],
                ["tool_runner", "validator"],
                ["validator", "reviewer"],
            ],
            "purpose": "change-validation",
        },
    ),
]

DEMO_MODELS = [
    ModelSeed(
        name="internal-llm-gateway",
        provider="internal",
        base_url="https://model-gateway.local",
        auth_type="bearer",
        version="v1",
        model_name="ops-model",
        tokenizer_name="ops-tokenizer",
        context_window=8192,
        pricing={"input_per_1k": 0.001, "output_per_1k": 0.002},
        capabilities={"chat": True, "tools": True, "streaming": False},
    ),
    ModelSeed(
        name="internal-analyst-gateway",
        provider="internal",
        base_url="https://analyst-gateway.local",
        auth_type="bearer",
        version="v1",
        model_name="analyst-model",
        tokenizer_name="analyst-tokenizer",
        context_window=16384,
        pricing={"input_per_1k": 0.0015, "output_per_1k": 0.0025},
        capabilities={"chat": True, "tools": True, "streaming": True},
    ),
]

DEMO_ENVIRONMENTS = [
    EnvironmentSeed(
        name="dev",
        description="Локальное окружение разработки и smoke-проверок.",
        labels={"tier": "development", "managed_by": "workflow-platform"},
    ),
    EnvironmentSeed(
        name="prod",
        description="Демонстрационное production-окружение для эксплуатационных сценариев.",
        labels={"tier": "production", "criticality": "high", "managed_by": "workflow-platform"},
    ),
]

DEMO_AGENTS = [
    AgentSeed(
        name="billing-ops-agent",
        description="Агент сопровождения платежного контура и диагностики деградаций.",
        owner="platform-team",
        version="v1",
        graph_name="billing-operations-graph",
        tags={"domain": "billing", "team": "platform", "seeded": True},
        runtime_config={"timeout_seconds": 30, "max_retries": 2, "validation_required": False},
    ),
    AgentSeed(
        name="support-triage-agent",
        description="Агент триажа пользовательских обращений и инцидентов поддержки.",
        owner="support-platform",
        version="v1",
        graph_name="billing-operations-graph",
        tags={"domain": "support", "team": "operations", "seeded": True},
        runtime_config={"timeout_seconds": 20, "max_retries": 1, "validation_required": False},
    ),
    AgentSeed(
        name="deployment-review-agent",
        description="Агент проверки рискованных rollout-сценариев перед выпуском изменений.",
        owner="release-engineering",
        version="v1",
        graph_name="validator-enabled-graph",
        tags={"domain": "delivery", "team": "release", "seeded": True},
        runtime_config={"timeout_seconds": 45, "max_retries": 2, "validation_required": True},
    ),
]

DEMO_DEPLOYMENTS = [
    DeploymentSeed(
        seed_key="billing-ops-agent-dev",
        agent_name="billing-ops-agent",
        agent_version="v1",
        model_name="internal-llm-gateway",
        model_version="v1",
        environment_name="dev",
        replica_count=1,
        configuration={"mode": "development", "validation_required": False, "seeded": True},
    ),
    DeploymentSeed(
        seed_key="support-triage-agent-prod",
        agent_name="support-triage-agent",
        agent_version="v1",
        model_name="internal-llm-gateway",
        model_version="v1",
        environment_name="prod",
        replica_count=2,
        configuration={"mode": "production", "validation_required": False, "seeded": True},
    ),
    DeploymentSeed(
        seed_key="deployment-review-agent-prod",
        agent_name="deployment-review-agent",
        agent_version="v1",
        model_name="internal-analyst-gateway",
        model_version="v1",
        environment_name="prod",
        replica_count=1,
        configuration={"mode": "production", "validation_required": True, "seeded": True},
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Идемпотентно создает demo graph, agents, models, environments и deployments."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Базовый URL локального API.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ENV_FILE,
        help="Путь до .env-файла, из которого читаются API key и database URL.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Таймаут ожидания materialized read-side после публикации событий.",
    )
    return parser.parse_args()


def parse_env_map(env_file: Path) -> dict[str, str]:
    # Скрипт сознательно читает .env сам, потому что запускается как внешняя
    # operational утилита и не должен зависеть от FastAPI settings bootstrap.
    values: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def get_first_env_value(raw_value: str) -> str:
    trimmed = raw_value.strip()
    if trimmed.startswith("["):
        parsed = json.loads(trimmed)
        if isinstance(parsed, list):
            return str(parsed[0])
        return str(parsed)
    return trimmed.split(",", maxsplit=1)[0].strip()


def normalize_db_url(raw_url: str) -> str:
    # При запуске с хоста compose-имя `postgres` недоступно, поэтому URL
    # локально перенаправляется на localhost для прямого доступа к БД.
    parsed = urlparse(raw_url)
    if parsed.hostname not in {"postgres", "db"}:
        return raw_url
    netloc = parsed.netloc.replace(parsed.hostname, "localhost")
    return urlunparse(parsed._replace(netloc=netloc))


def http_json(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None
    request_headers = dict(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, method=method, headers=request_headers, data=body)
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_api(base_url: str, timeout_sec: int) -> None:
    deadline = time.time() + timeout_sec
    url = f"{base_url.rstrip('/')}/api/v1/health/ready"
    while time.time() < deadline:
        try:
            request = Request(url, method="GET")
            with urlopen(request, timeout=10) as response:
                if getattr(response, "status", 200) == 200:
                    return
        except (HTTPError, URLError):
            time.sleep(2)
    raise TimeoutError(f"Не удалось дождаться готовности API: {url}")


async def fetch_one_or_none(session: AsyncSession, query: Select[Any]) -> Any | None:
    return await session.scalar(query.limit(1))


async def wait_for_row(
    session_factory: async_sessionmaker[AsyncSession],
    query_builder: callable,
    timeout_sec: int,
) -> Any:
    # Seed публикует write-side команды асинхронно, поэтому между созданием
    # сущности и ее доступностью в read-side есть небольшое окно materialization lag.
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        async with session_factory() as session:
            entity = await fetch_one_or_none(session, query_builder())
            if entity is not None:
                return entity
        await asyncio.sleep(2)
    raise TimeoutError("Материализация demo-данных не завершилась в ожидаемое время.")


async def get_graph_by_name(session: AsyncSession, name: str) -> GraphDefinition | None:
    return await fetch_one_or_none(
        session,
        select(GraphDefinition).where(GraphDefinition.name == name),
    )


async def get_environment_by_name(session: AsyncSession, name: str) -> Environment | None:
    return await fetch_one_or_none(session, select(Environment).where(Environment.name == name))


async def get_agent_by_name(session: AsyncSession, name: str) -> Agent | None:
    return await fetch_one_or_none(session, select(Agent).where(Agent.name == name))


async def get_model_by_name(session: AsyncSession, name: str) -> ModelEndpoint | None:
    return await fetch_one_or_none(session, select(ModelEndpoint).where(ModelEndpoint.name == name))


async def get_agent_version(
    session: AsyncSession, agent_name: str, version: str
) -> AgentVersion | None:
    return await fetch_one_or_none(
        session,
        select(AgentVersion)
        .join(Agent, Agent.id == AgentVersion.agent_id)
        .where(Agent.name == agent_name, AgentVersion.version == version),
    )


async def get_model_version(
    session: AsyncSession, model_name: str, version: str
) -> ModelVersion | None:
    return await fetch_one_or_none(
        session,
        select(ModelVersion)
        .join(ModelEndpoint, ModelEndpoint.id == ModelVersion.model_endpoint_id)
        .where(ModelEndpoint.name == model_name, ModelVersion.version == version),
    )


async def get_deployment_by_seed_key(session: AsyncSession, seed_key: str) -> Deployment | None:
    return await fetch_one_or_none(
        session,
        select(Deployment).where(Deployment.configuration["seed_key"].as_string() == seed_key),
    )


async def seed_graphs(
    headers: Mapping[str, str],
    base_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    timeout_sec: int,
) -> list[str]:
    # Сначала создаются graph-ы, потому что на них опираются agent versions.
    actions: list[str] = []
    for graph in DEMO_GRAPHS:
        async with session_factory() as session:
            existing = await get_graph_by_name(session, graph.name)
        if existing is not None:
            actions.append(f"graph:{graph.name}:exists")
            continue
        http_json(
            "POST",
            f"{base_url}/api/v1/graphs",
            headers=headers,
            payload={
                "name": graph.name,
                "description": graph.description,
                "version": graph.version,
                "entrypoint": graph.entrypoint,
                "definition": graph.definition,
            },
        )
        await wait_for_row(
            session_factory,
            lambda graph_name=graph.name: select(GraphDefinition).where(
                GraphDefinition.name == graph_name
            ),
            timeout_sec,
        )
        actions.append(f"graph:{graph.name}:created")
    return actions


async def seed_models(
    headers: Mapping[str, str],
    base_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    timeout_sec: int,
) -> list[str]:
    # Модели создаются до deployment-ов, чтобы потом можно было найти их версии.
    actions: list[str] = []
    for model in DEMO_MODELS:
        async with session_factory() as session:
            existing = await get_model_by_name(session, model.name)
        if existing is not None:
            actions.append(f"model:{model.name}:exists")
            continue
        http_json(
            "POST",
            f"{base_url}/api/v1/models",
            headers=headers,
            payload={
                "name": model.name,
                "provider": model.provider,
                "base_url": model.base_url,
                "auth_type": model.auth_type,
                "capabilities": model.capabilities,
                "version": model.version,
                "model_name": model.model_name,
                "tokenizer_name": model.tokenizer_name,
                "context_window": model.context_window,
                "pricing": model.pricing,
                "is_default": True,
            },
        )
        await wait_for_row(
            session_factory,
            lambda model_name=model.name: select(ModelEndpoint).where(
                ModelEndpoint.name == model_name
            ),
            timeout_sec,
        )
        actions.append(f"model:{model.name}:created")
    return actions


async def seed_environments(
    headers: Mapping[str, str],
    base_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    timeout_sec: int,
) -> list[str]:
    actions: list[str] = []
    for environment in DEMO_ENVIRONMENTS:
        async with session_factory() as session:
            existing = await get_environment_by_name(session, environment.name)
        if existing is not None:
            actions.append(f"environment:{environment.name}:exists")
            continue
        http_json(
            "POST",
            f"{base_url}/api/v1/environments",
            headers=headers,
            payload={
                "name": environment.name,
                "description": environment.description,
                "labels": environment.labels,
            },
        )
        await wait_for_row(
            session_factory,
            lambda env_name=environment.name: select(Environment).where(
                Environment.name == env_name
            ),
            timeout_sec,
        )
        actions.append(f"environment:{environment.name}:created")
    return actions


async def seed_agents(
    headers: Mapping[str, str],
    base_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    timeout_sec: int,
) -> list[str]:
    # Агент seed deliberately дожидается materialization agent version, потому что
    # deployment contract ссылается именно на version id, а не только на agent id.
    actions: list[str] = []
    for agent in DEMO_AGENTS:
        async with session_factory() as session:
            existing = await get_agent_by_name(session, agent.name)
            graph = await get_graph_by_name(session, agent.graph_name)
        if graph is None:
            raise RuntimeError(f"Не найден graph для demo-агента: {agent.graph_name}")
        if existing is not None:
            actions.append(f"agent:{agent.name}:exists")
            continue
        http_json(
            "POST",
            f"{base_url}/api/v1/agents",
            headers=headers,
            payload={
                "name": agent.name,
                "description": agent.description,
                "owner": agent.owner,
                "tags": agent.tags,
                "version": agent.version,
                "graph_definition_id": graph.id,
                "runtime_config": agent.runtime_config,
            },
        )
        await wait_for_row(
            session_factory,
            lambda agent_name=agent.name, version=agent.version: (
                select(AgentVersion)
                .join(Agent, Agent.id == AgentVersion.agent_id)
                .where(Agent.name == agent_name, AgentVersion.version == version)
            ),
            timeout_sec,
        )
        actions.append(f"agent:{agent.name}:created")
    return actions


async def seed_deployments(
    headers: Mapping[str, str],
    base_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    timeout_sec: int,
) -> list[str]:
    # Deployment-ы создаются последними, когда уже есть agent/model version ids
    # и environment ids, на которые можно безопасно сослаться.
    actions: list[str] = []
    for deployment in DEMO_DEPLOYMENTS:
        async with session_factory() as session:
            existing = await get_deployment_by_seed_key(session, deployment.seed_key)
            agent_version = await get_agent_version(
                session, deployment.agent_name, deployment.agent_version
            )
            model_version = await get_model_version(
                session, deployment.model_name, deployment.model_version
            )
            environment = await get_environment_by_name(session, deployment.environment_name)
        if existing is not None:
            actions.append(f"deployment:{deployment.seed_key}:exists")
            continue
        if agent_version is None:
            raise RuntimeError(
                f"Не найдена версия агента {deployment.agent_name}:{deployment.agent_version}"
            )
        if model_version is None:
            raise RuntimeError(
                f"Не найдена версия модели {deployment.model_name}:{deployment.model_version}"
            )
        if environment is None:
            raise RuntimeError(f"Не найдено окружение {deployment.environment_name}")
        http_json(
            "POST",
            f"{base_url}/api/v1/deployments",
            headers=headers,
            payload={
                "agent_version_id": agent_version.id,
                "model_version_id": model_version.id,
                "environment_id": environment.id,
                "environment_name": environment.name,
                "environment_description": environment.description,
                "replica_count": deployment.replica_count,
                "configuration": {
                    **deployment.configuration,
                    "seed_key": deployment.seed_key,
                },
            },
        )
        await wait_for_row(
            session_factory,
            lambda seed_key=deployment.seed_key: (
                select(Deployment).where(
                    Deployment.configuration["seed_key"].as_string() == seed_key
                )
            ),
            timeout_sec,
        )
        actions.append(f"deployment:{deployment.seed_key}:created")
    return actions


async def print_summary(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        agents = [
            agent.name
            for agent in (await session.scalars(select(Agent).order_by(Agent.name))).all()
        ]
        graphs = [
            graph.name
            for graph in (
                await session.scalars(select(GraphDefinition).order_by(GraphDefinition.name))
            ).all()
        ]
        environments = [
            environment.name
            for environment in (
                await session.scalars(select(Environment).order_by(Environment.name))
            ).all()
        ]
        deployments = (
            await session.scalars(
                select(Deployment).where(Deployment.configuration["seed_key"].as_string().is_not(None))
            )
        ).all()
    print()
    print("Demo-данные готовы.")
    print(f"Graphs       : {', '.join(graphs)}")
    print(f"Agents       : {', '.join(agents)}")
    print(f"Environments : {', '.join(environments)}")
    print(f"Deployments  : {len(deployments)} seeded entries")


async def run() -> None:
    args = parse_args()
    env_values = parse_env_map(args.env_file)
    api_key = get_first_env_value(env_values["API_KEYS"])
    database_url = normalize_db_url(env_values["DATABASE_URL"])
    base_url = args.base_url.rstrip("/")
    headers = {"X-API-Key": api_key}

    wait_for_api(base_url, args.timeout_sec)

    engine: AsyncEngine = create_async_engine(database_url, future=True, pool_pre_ping=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    actions: list[str] = []
    try:
        actions.extend(await seed_graphs(headers, base_url, session_factory, args.timeout_sec))
        actions.extend(await seed_models(headers, base_url, session_factory, args.timeout_sec))
        actions.extend(
            await seed_environments(headers, base_url, session_factory, args.timeout_sec)
        )
        actions.extend(await seed_agents(headers, base_url, session_factory, args.timeout_sec))
        actions.extend(await seed_deployments(headers, base_url, session_factory, args.timeout_sec))
        for action in actions:
            print(action)
        await print_summary(session_factory)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
