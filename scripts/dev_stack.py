from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Скрипт является единым локальным bootstrap entrypoint для Docker-окружения.
# Он intentionally не зависит от внутренних Python runtime-объектов приложения,
# а работает как внешний операторский инструмент: проверяет Docker, поднимает
# compose stack, выполняет seed и запускает smoke-проверку публичного API.
ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE_FILE = ROOT / ".env.example"
EXECUTION_EXAMPLE_FILE = ROOT / "examples" / "workflow_execution_with_validator.json"
SEED_SCRIPT_FILE = ROOT / "scripts" / "seed_demo_data.py"
DEFAULT_TIMEOUT_SECONDS = 240


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Локальный bootstrap Docker-стека для разработки"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Поднять локальный стек")
    start_parser.add_argument(
        "--no-build",
        action="store_true",
        help="Не пересобирать Docker-образы перед запуском",
    )
    start_parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Не запускать smoke-проверку после старта",
    )
    start_parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Не создавать demo-данные после старта",
    )
    start_parser.add_argument(
        "--timeout-sec",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Таймаут ожидания readiness API",
    )

    smoke_parser = subparsers.add_parser("smoke", help="Прогнать smoke-проверку")
    smoke_parser.add_argument(
        "--timeout-sec",
        type=int,
        default=30,
        help="Таймаут ожидания materialized read-side execution",
    )

    seed_parser = subparsers.add_parser("seed", help="Создать demo-данные")
    seed_parser.add_argument(
        "--timeout-sec",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Таймаут ожидания materialized demo-данных",
    )

    stop_parser = subparsers.add_parser("stop", help="Остановить локальный стек")
    stop_parser.add_argument(
        "--volumes",
        action="store_true",
        help="Удалить volumes при остановке",
    )

    return parser.parse_args()


def run_command(args: list[str]) -> None:
    # Все внешние команды выполняются из корня репозитория, чтобы одинаково
    # работали compose, uv и относительные пути независимо от cwd пользователя.
    completed = subprocess.run(args, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def ensure_docker_available() -> None:
    for command in (["docker", "info"], ["docker", "compose", "version"]):
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Docker недоступен. Убедитесь, что Docker Desktop запущен "
                "и docker compose установлен."
            )


def ensure_env_file() -> None:
    # Локальная разработка должна стартовать даже в "чистом" клоне репозитория,
    # поэтому .env автоматически создается из example-файла при первом запуске.
    if not ENV_FILE.exists():
        ENV_FILE.write_text(ENV_EXAMPLE_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        print("Создан локальный .env из .env.example")
    normalize_env_file()


def normalize_env_file() -> None:
    # Некоторые настройки ожидаются Pydantic как JSON-массивы, а локальный пользователь
    # может заполнить их CSV-строкой. Нормализация делает bootstrap устойчивым.
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    normalized: list[str] = []
    for line in lines:
        value = line.partition("=")[2].strip()
        if line.startswith("KAFKA_BOOTSTRAP_SERVERS=") and not value.startswith("["):
            normalized.append('KAFKA_BOOTSTRAP_SERVERS=["kafka:9092"]')
            continue
        if line.startswith("API_KEYS=") and not value.startswith("["):
            normalized.append('API_KEYS=["replace-with-api-key"]')
            continue
        normalized.append(line)
    ENV_FILE.write_text("\n".join(normalized) + "\n", encoding="utf-8")


def wait_for_url(url: str, timeout_sec: int) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            request = Request(url, method="GET")
            with urlopen(request, timeout=10) as response:
                status = getattr(response, "status", 200)
                if 200 <= status < 500:
                    return
        except (HTTPError, URLError):
            time.sleep(3)
            continue
        time.sleep(3)
    raise TimeoutError(f"Таймаут ожидания доступности URL: {url}")


def parse_env_map() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key] = value
    return values


def get_first_env_value(raw_value: str) -> str:
    trimmed = raw_value.strip()
    if trimmed.startswith("["):
        parsed = json.loads(trimmed)
        if isinstance(parsed, list):
            return str(parsed[0])
        return str(parsed)
    return trimmed.split(",", maxsplit=1)[0].strip()


def http_json(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None
    request_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, method=method, headers=request_headers, data=body)
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def http_status(url: str) -> int:
    request = Request(url, method="GET")
    with urlopen(request, timeout=15) as response:
        return int(getattr(response, "status", 200))


def wait_for_execution_projection(
    execution_id: str,
    headers: Mapping[str, str],
    timeout_sec: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    url = f"http://localhost:8080/api/v1/executions/{execution_id}"
    while time.time() < deadline:
        try:
            return http_json("GET", url, headers=headers)
        except (HTTPError, URLError):
            time.sleep(2)
    raise TimeoutError(f"Проекция execution не появилась за {timeout_sec}с: {execution_id}")


def run_smoke(timeout_sec: int) -> None:
    # Smoke deliberately проверяет платформу через публичные HTTP endpoints, а не
    # через внутренние Python вызовы, чтобы валидировать реальный локальный стек.
    env_values = parse_env_map()
    api_key = get_first_env_value(env_values["API_KEYS"])
    headers = {"X-API-Key": api_key}

    print("Проверка /api/v1/health/live")
    live = http_json("GET", "http://localhost:8080/api/v1/health/live", headers=headers)

    print("Проверка /api/v1/health/ready")
    ready = http_json("GET", "http://localhost:8080/api/v1/health/ready", headers=headers)

    print("Проверка /docs")
    docs_status = http_status("http://localhost:8080/docs")
    if docs_status != 200:
        raise RuntimeError("Swagger UI недоступен")

    print("Запуск тестового сценария")
    execution_payload = json.loads(EXECUTION_EXAMPLE_FILE.read_text(encoding="utf-8"))
    execution = http_json(
        "POST",
        "http://localhost:8080/api/v1/executions",
        headers=headers,
        payload=execution_payload,
    )

    time.sleep(2)
    execution_state = wait_for_execution_projection(execution["entity_id"], headers, timeout_sec)
    step_names = ", ".join(step["step_name"] for step in execution_state["steps"])

    print()
    print(f"LiveStatus      : {live['status']}")
    print(f"ReadyStatus     : {ready['status']}")
    print(f"ExecutionId     : {execution['entity_id']}")
    print(f"ExecutionStatus : {execution_state['status']}")
    print(f"StepNames       : {step_names}")


def run_seed(timeout_sec: int) -> None:
    # Seed вынесен в отдельный скрипт, но dev_stack orchestrates его как часть
    # общего bootstrap flow, чтобы после старта API не был "пустым".
    run_command(
        [
            sys.executable,
            str(SEED_SCRIPT_FILE),
            "--timeout-sec",
            str(timeout_sec),
        ]
    )


def start_stack(no_build: bool, skip_seed: bool, skip_smoke: bool, timeout_sec: int) -> None:
    # Основной happy path локальной разработки: поднять стек, дождаться API,
    # наполнить реестр demo-данными и optionally прогнать smoke.
    ensure_docker_available()
    ensure_env_file()
    compose_args = ["docker", "compose", "up", "-d"]
    if not no_build:
        compose_args.append("--build")

    print("Запуск docker compose...")
    run_command(compose_args)

    print("Ожидание готовности API...")
    wait_for_url("http://localhost:8080/api/v1/health/ready", timeout_sec)

    print("Текущее состояние контейнеров:")
    run_command(["docker", "compose", "ps"])

    if not skip_seed:
        print("Создание demo-данных...")
        run_seed(timeout_sec=timeout_sec)

    if not skip_smoke:
        print("Запуск smoke-проверки...")
        run_smoke(timeout_sec=30)

    print("Локальный стек поднят.")


def stop_stack(volumes: bool) -> None:
    # Остановка остается симметричной старту, чтобы developer workflow был
    # предсказуемым и не требовал ручного compose lifecycle management.
    ensure_docker_available()
    args = ["docker", "compose", "down"]
    if volumes:
        args.append("-v")
    run_command(args)
    print("Локальный стек остановлен.")


def main() -> None:
    args = parse_args()
    if args.command == "start":
        start_stack(
            no_build=bool(args.no_build),
            skip_seed=bool(args.skip_seed),
            skip_smoke=bool(args.skip_smoke),
            timeout_sec=int(args.timeout_sec),
        )
        return
    if args.command == "smoke":
        run_smoke(timeout_sec=int(args.timeout_sec))
        return
    if args.command == "seed":
        run_seed(timeout_sec=int(args.timeout_sec))
        return
    if args.command == "stop":
        stop_stack(volumes=bool(args.volumes))
        return
    raise RuntimeError(f"Неизвестная команда: {args.command}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
