"""Integration tests for the CDC pipeline: Postgres write -> Debezium -> Kafka.

Requires the real stack. Start it first:

    docker compose up -d
    ./scripts/register-debezium-connector.sh

Run with:

    pytest -m integration
"""

import json
import uuid

import pytest

from tests.conftest import wait_for_message

pytestmark = pytest.mark.integration


def _after(payload):
    return payload["payload"]["after"] if "payload" in payload else payload["after"]


def test_device_insert_produces_a_cdc_event_on_kafka(postgres_connection, kafka_connect_registered):
    device_code = f"itest-device-{uuid.uuid4().hex[:8]}"

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO devices (device_code, site, device_type)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (device_code, "integration-test-site", "sensor"),
        )
        device_id = cursor.fetchone()[0]

    payload = wait_for_message(
        "iot.public.devices",
        lambda p: _after(p).get("device_code") == device_code,
        timeout_seconds=20,
    )
    assert payload is not None, "no CDC event observed on iot.public.devices within timeout"

    after = _after(json.loads(payload))
    assert after["id"] == device_id
    assert after["device_code"] == device_code


def test_telemetry_insert_produces_a_cdc_event_on_kafka(postgres_connection, kafka_connect_registered):
    device_code = f"itest-device-{uuid.uuid4().hex[:8]}"

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO devices (device_code, site, device_type)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (device_code, "integration-test-site", "sensor"),
        )
        device_id = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO telemetry (device_id, temperature, humidity)
            VALUES (%s, %s, %s)
            """,
            (device_id, 27.3, 41.0),
        )

    payload = wait_for_message(
        "iot.public.telemetry",
        lambda p: _after(p).get("device_id") == device_id,
        timeout_seconds=20,
    )
    assert payload is not None, "no CDC event observed on iot.public.telemetry within timeout"

    after = _after(json.loads(payload))
    assert after["device_id"] == device_id
