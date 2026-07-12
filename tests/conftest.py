"""Shared fixtures for the integration/e2e suite.

These tests exercise the real docker-compose stack (Postgres + Kafka +
Debezium) and, for e2e, a running Django server -- see
docs/TESTING_GUIDELINES.md #5. Every fixture skips (rather than errors) when the
dependency it needs isn't reachable, so `pytest -m integration` gives a clear
"start the stack first" message instead of a confusing connection traceback.
"""

import json
import os
import time

import psycopg2
import pytest
import requests

POSTGRES_DSN = {
    "host": os.environ.get("POSTGRES_HOST", "localhost"),
    "port": os.environ.get("POSTGRES_PORT", "5432"),
    "dbname": os.environ.get("POSTGRES_DB", "iot_operational"),
    "user": os.environ.get("POSTGRES_USER", "iot_app"),
    "password": os.environ.get("POSTGRES_PASSWORD", "iot_app_password"),
}
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_CONNECT_URL = os.environ.get("KAFKA_CONNECT_URL", "http://localhost:8083")
DJANGO_BASE_URL = os.environ.get("DJANGO_BASE_URL", "http://localhost:8000")


def _require_reachable(check, message):
    try:
        check()
    except Exception as exc:  # noqa: BLE001 -- any connection failure means "skip"
        pytest.skip(f"{message}: {exc}")


@pytest.fixture(scope="session")
def postgres_connection():
    conn_holder = {}
    _require_reachable(
        lambda: conn_holder.update(conn=psycopg2.connect(**POSTGRES_DSN)),
        "Postgres is not reachable -- run `docker compose up -d` first",
    )
    conn = conn_holder["conn"]
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def kafka_connect_registered():
    def check():
        response = requests.get(f"{KAFKA_CONNECT_URL}/connectors/iot-postgres-connector/status", timeout=5)
        response.raise_for_status()
        status = response.json()["connector"]["state"]
        assert status == "RUNNING", f"connector state is {status!r}, expected RUNNING"

    _require_reachable(
        check,
        "Debezium connector is not registered/running -- run "
        "`docker compose up -d && ./scripts/register-debezium-connector.sh` first",
    )


@pytest.fixture(scope="session")
def django_server_reachable():
    def check():
        requests.get(f"{DJANGO_BASE_URL}/dashboard/summary", timeout=5).raise_for_status()

    _require_reachable(
        check,
        f"Django server is not reachable at {DJANGO_BASE_URL} -- run "
        "`cd django_app && python manage.py runserver` first",
    )
    return DJANGO_BASE_URL


def wait_for_message(topic, predicate, timeout_seconds=20):
    """Scans `topic` from the beginning until a message satisfying
    `predicate(payload_dict)` is found, or `timeout_seconds` elapses.

    Matches by content (e.g. a test-run-unique device_code) rather than by
    "the next message after I subscribe" -- a consumer positioned at the
    tail can lose the race against Debezium and end up past the event it's
    looking for if the write happens (or another test's write already
    happened) before/while it's establishing its offset."""
    from kafka import KafkaConsumer

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        auto_offset_reset="earliest",
        value_deserializer=lambda v: v.decode("utf-8") if v is not None else None,
    )
    deadline = time.monotonic() + timeout_seconds
    try:
        while time.monotonic() < deadline:
            records = consumer.poll(timeout_ms=1000)
            for topic_partition_records in records.values():
                for record in topic_partition_records:
                    if record.value is None:
                        continue
                    if predicate(json.loads(record.value)):
                        return record.value
        return None
    finally:
        consumer.close()
