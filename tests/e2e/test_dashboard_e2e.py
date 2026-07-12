"""End-to-end test covering the full path in README.md's data flow diagram:

    IoT device write -> Postgres -> Debezium CDC -> Kafka
                                                        |
    Dashboard client <- Django API <- (Snowflake, mocked here) <-+

Snowflake itself isn't part of this local stack (see docs/CODING_GUIDELINES.md #1
and #3), so this test verifies the CDC half against the real docker-compose
stack, and the API half against the running Django server, which serves
`/dashboard/*` from `MockSnowflakeClient` when SNOWFLAKE_ACCOUNT is unset.

Requires, in three separate terminals:

    docker compose up -d
    ./scripts/register-debezium-connector.sh
    cd django_app && python manage.py runserver

Run with:

    pytest -m e2e
"""

import json
import uuid

import pytest
import requests

from tests.conftest import consume_latest_message

pytestmark = pytest.mark.e2e


def test_device_telemetry_flows_from_postgres_to_kafka_and_api_serves_dashboard_data(
    postgres_connection, kafka_connect_registered, django_server_reachable
):
    device_code = f"e2e-device-{uuid.uuid4().hex[:8]}"

    # 1. An IoT device registers and reports telemetry into the operational database.
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO devices (device_code, site, device_type)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (device_code, "e2e-site", "sensor"),
        )
        device_id = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO telemetry (device_id, temperature, humidity)
            VALUES (%s, %s, %s)
            """,
            (device_id, 28.4, 55.0),
        )

    # 2. Debezium captures both writes and publishes them to Kafka.
    device_event = consume_latest_message("iot.public.devices", timeout_seconds=20)
    telemetry_event = consume_latest_message("iot.public.telemetry", timeout_seconds=20)
    assert device_event is not None, "device insert never reached Kafka"
    assert telemetry_event is not None, "telemetry insert never reached Kafka"

    device_payload = json.loads(device_event)
    device_after = (
        device_payload["payload"]["after"] if "payload" in device_payload else device_payload["after"]
    )
    assert device_after["device_code"] == device_code

    # 3. The Django dashboard API is independently reachable and serves the
    #    analytics-side contract (summary/devices/site/alerts), regardless of
    #    which specific device just landed in the operational database --
    #    real deployments read this from Snowflake's aggregated tables, not
    #    from the row just inserted above.
    base_url = django_server_reachable
    for path in ["/dashboard/summary", "/dashboard/devices", "/dashboard/alerts"]:
        response = requests.get(f"{base_url}{path}", timeout=5)
        assert response.status_code == 200
        assert response.json(), f"{path} returned no rows"

    summary_row = requests.get(f"{base_url}/dashboard/summary", timeout=5).json()[0]
    assert set(summary_row.keys()) == {"window_start", "site", "avg_temp", "max_temp", "alert_count"}
