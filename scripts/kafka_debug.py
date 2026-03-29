from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BOOTSTRAP_SERVER = "localhost:9092"
DEFAULT_KAFKA_SERVICE = "kafka"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Локальная диагностика Kafka через docker compose"
    )
    parser.add_argument(
        "--service",
        default=DEFAULT_KAFKA_SERVICE,
        help="Имя Kafka-сервиса в docker compose",
    )
    parser.add_argument(
        "--bootstrap-server",
        default=DEFAULT_BOOTSTRAP_SERVER,
        help="Bootstrap server внутри Kafka CLI",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("topics", help="Показать список топиков")
    subparsers.add_parser("groups", help="Показать список consumer groups")
    subparsers.add_parser("lag", help="Показать lag всех consumer groups")

    dlq_parser = subparsers.add_parser("dlq", help="Показать только DLQ-топики")
    dlq_parser.add_argument(
        "--describe",
        action="store_true",
        help="Дополнительно показать описание DLQ-топиков",
    )

    describe_topic_parser = subparsers.add_parser("describe-topic", help="Описать Kafka topic")
    describe_topic_parser.add_argument("topic", help="Имя topic")

    describe_group_parser = subparsers.add_parser(
        "describe-group", help="Описать consumer group и lag"
    )
    describe_group_parser.add_argument("group", help="Имя consumer group")

    peek_topic_parser = subparsers.add_parser(
        "peek-topic", help="Прочитать несколько сообщений из topic"
    )
    peek_topic_parser.add_argument("topic", help="Имя topic")
    peek_topic_parser.add_argument(
        "--max-messages",
        type=int,
        default=3,
        help="Сколько сообщений прочитать",
    )
    peek_topic_parser.add_argument(
        "--from-beginning",
        action="store_true",
        help="Читать с начала topic",
    )
    add_peek_filters(peek_topic_parser)

    peek_dlq_parser = subparsers.add_parser(
        "peek-dlq", help="Прочитать несколько сообщений из DLQ-topic"
    )
    peek_dlq_parser.add_argument("topic", help="Имя DLQ-topic")
    peek_dlq_parser.add_argument(
        "--max-messages",
        type=int,
        default=3,
        help="Сколько сообщений прочитать",
    )
    peek_dlq_parser.add_argument(
        "--from-beginning",
        action="store_true",
        help="Читать с начала topic",
    )
    add_peek_filters(peek_dlq_parser)

    subparsers.add_parser("all", help="Показать topics, groups, lag и DLQ одним запуском")
    return parser.parse_args()


def add_peek_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--event-type", help="Фильтр по envelope.event_type")
    parser.add_argument("--correlation-id", help="Фильтр по envelope.correlation_id")
    parser.add_argument("--trace-id", help="Фильтр по envelope.trace_id")
    parser.add_argument("--entity-id", help="Фильтр по envelope.entity_id")
    parser.add_argument(
        "--payload-field",
        action="append",
        default=[],
        metavar="PATH=VALUE",
        help=(
            "Фильтр по вложенному полю payload, например "
            "--payload-field execution_run.id=<id> или execution_run_id=<id>"
        ),
    )


def run_kafka_cli(service: str, shell_command: str) -> str:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        service,
        "bash",
        "-lc",
        shell_command,
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        error_output = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(error_output or "Kafka CLI завершился с ошибкой")
    return completed.stdout.strip()


def print_section(title: str, body: str) -> None:
    print(f"\n=== {title} ===")
    print(body if body else "(пусто)")


def list_topics(service: str, bootstrap_server: str) -> str:
    command = (
        "kafka-topics --bootstrap-server "
        f"{shlex.quote(bootstrap_server)} --list | sort"
    )
    return run_kafka_cli(service, command)


def describe_topic(service: str, bootstrap_server: str, topic: str) -> str:
    command = (
        "kafka-topics --bootstrap-server "
        f"{shlex.quote(bootstrap_server)} --describe --topic {shlex.quote(topic)}"
    )
    return run_kafka_cli(service, command)


def list_groups(service: str, bootstrap_server: str) -> str:
    command = (
        "kafka-consumer-groups --bootstrap-server "
        f"{shlex.quote(bootstrap_server)} --list | sort"
    )
    return run_kafka_cli(service, command)


def describe_group(service: str, bootstrap_server: str, group: str) -> str:
    command = (
        "kafka-consumer-groups --bootstrap-server "
        f"{shlex.quote(bootstrap_server)} --describe --group {shlex.quote(group)}"
    )
    return run_kafka_cli(service, command)


def collect_lag(service: str, bootstrap_server: str) -> str:
    groups_output = list_groups(service, bootstrap_server)
    groups = [group.strip() for group in groups_output.splitlines() if group.strip()]
    if not groups:
        return ""

    sections: list[str] = []
    for group in groups:
        group_description = describe_group(service, bootstrap_server, group)
        sections.append(f"[{group}]\n{group_description}")
    return "\n\n".join(sections)


def collect_dlq_topics(service: str, bootstrap_server: str, describe: bool) -> str:
    topics = [
        topic.strip()
        for topic in list_topics(service, bootstrap_server).splitlines()
        if topic.strip().endswith(".dlq")
    ]
    if not topics:
        return ""
    if not describe:
        return "\n".join(topics)
    sections = [
        f"[{topic}]\n{describe_topic(service, bootstrap_server, topic)}"
        for topic in topics
    ]
    return "\n\n".join(sections)


def consume_messages(
    service: str,
    bootstrap_server: str,
    topic: str,
    *,
    max_messages: int,
    from_beginning: bool,
) -> str:
    from_beginning_flag = "--from-beginning" if from_beginning else ""
    raw_fetch_limit = max_messages * 20
    command = (
        "kafka-console-consumer "
        f"--bootstrap-server {shlex.quote(bootstrap_server)} "
        f"--topic {shlex.quote(topic)} "
        f"{from_beginning_flag} "
        f"--max-messages {raw_fetch_limit} "
        "--timeout-ms 3000 "
        "--property print.headers=true "
        "--property print.key=true "
        "--property print.timestamp=true"
    )
    return run_kafka_cli(service, " ".join(command.split()))


def parse_message_line(line: str) -> dict[str, object] | None:
    parts = line.split("\t", maxsplit=3)
    if len(parts) != 4:
        return None
    timestamp, headers, key, value = parts
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        payload = value
    return {
        "timestamp": timestamp,
        "headers": headers,
        "key": key,
        "value": payload,
    }


def get_nested_value(payload: object, path: str) -> object | None:
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def matches_filters(message: dict[str, object], args: argparse.Namespace) -> bool:
    value = message.get("value")
    if not isinstance(value, dict):
        return False

    direct_filters = {
        "event_type": getattr(args, "event_type", None),
        "correlation_id": getattr(args, "correlation_id", None),
        "trace_id": getattr(args, "trace_id", None),
        "entity_id": getattr(args, "entity_id", None),
    }
    for field_name, expected in direct_filters.items():
        if expected and str(value.get(field_name)) != str(expected):
            return False

    for raw_filter in cast_sequence_str(getattr(args, "payload_field", [])):
        if "=" not in raw_filter:
            return False
        path, expected = raw_filter.split("=", maxsplit=1)
        actual = get_nested_value(value.get("payload"), path)
        if str(actual) != expected:
            return False
    return True


def cast_sequence_str(value: object) -> Sequence[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def pretty_print_messages(raw_output: str, args: argparse.Namespace) -> str:
    lines = [line for line in raw_output.splitlines() if line.strip()]
    if not lines:
        return "(сообщения не найдены)"

    formatted_blocks: list[str] = []
    for line in lines:
        if line.startswith("Processed a total of"):
            continue
        message = parse_message_line(line)
        if message is None:
            formatted_blocks.append(line)
            continue
        if not matches_filters(message, args):
            continue
        pretty_payload = json.dumps(message["value"], ensure_ascii=False, indent=2)
        formatted_blocks.append(
            "\n".join(
                [
                    f"timestamp: {message['timestamp']}",
                    f"headers:   {message['headers']}",
                    f"key:       {message['key']}",
                    "value:",
                    pretty_payload,
                ]
            )
        )
        if len(formatted_blocks) >= int(args.max_messages):
            break
    if not formatted_blocks:
        return "(сообщения по заданным фильтрам не найдены)"
    return "\n\n---\n\n".join(formatted_blocks)


def main() -> None:
    args = parse_args()
    service = str(args.service)
    bootstrap_server = str(args.bootstrap_server)

    if args.command == "topics":
        print(list_topics(service, bootstrap_server))
        return
    if args.command == "groups":
        print(list_groups(service, bootstrap_server))
        return
    if args.command == "lag":
        print(collect_lag(service, bootstrap_server))
        return
    if args.command == "dlq":
        print(collect_dlq_topics(service, bootstrap_server, describe=bool(args.describe)))
        return
    if args.command == "describe-topic":
        print(describe_topic(service, bootstrap_server, str(args.topic)))
        return
    if args.command == "describe-group":
        print(describe_group(service, bootstrap_server, str(args.group)))
        return
    if args.command == "peek-topic":
        raw_output = consume_messages(
            service,
            bootstrap_server,
            str(args.topic),
            max_messages=int(args.max_messages),
            from_beginning=bool(args.from_beginning),
        )
        print(pretty_print_messages(raw_output, args))
        return
    if args.command == "peek-dlq":
        raw_output = consume_messages(
            service,
            bootstrap_server,
            str(args.topic),
            max_messages=int(args.max_messages),
            from_beginning=bool(args.from_beginning),
        )
        print(pretty_print_messages(raw_output, args))
        return
    if args.command == "all":
        print_section("Kafka Topics", list_topics(service, bootstrap_server))
        print_section("Consumer Groups", list_groups(service, bootstrap_server))
        print_section("Consumer Lag", collect_lag(service, bootstrap_server))
        print_section("DLQ Topics", collect_dlq_topics(service, bootstrap_server, describe=False))
        return
    raise RuntimeError(f"Неизвестная команда: {args.command}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
