from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
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

    subparsers.add_parser("all", help="Показать topics, groups, lag и DLQ одним запуском")
    return parser.parse_args()


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
