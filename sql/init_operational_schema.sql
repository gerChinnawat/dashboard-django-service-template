-- Operational schema (PostgreSQL OLTP).
-- Captured by Debezium and streamed into Kafka for downstream consumers.

CREATE TABLE IF NOT EXISTS devices (
    id              SERIAL PRIMARY KEY,
    device_code     VARCHAR(64) UNIQUE NOT NULL,
    site            VARCHAR(64) NOT NULL,
    device_type     VARCHAR(64) NOT NULL,
    config          JSONB NOT NULL DEFAULT '{}',
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS telemetry (
    id              BIGSERIAL PRIMARY KEY,
    device_id       INTEGER NOT NULL REFERENCES devices(id),
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    temperature     NUMERIC(6, 2),
    humidity        NUMERIC(6, 2),
    metadata        JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS alerts (
    id              BIGSERIAL PRIMARY KEY,
    device_id       INTEGER NOT NULL REFERENCES devices(id),
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    severity        VARCHAR(32) NOT NULL,
    message         TEXT NOT NULL,
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_telemetry_device_recorded ON telemetry (device_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_alerts_device_triggered ON alerts (device_id, triggered_at);

-- Logical replication is required for Debezium CDC.
ALTER SYSTEM SET wal_level = logical;

-- Publication used by the Debezium pgoutput plugin.
CREATE PUBLICATION iot_publication FOR TABLE devices, telemetry, alerts;
