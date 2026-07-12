#!/usr/bin/env bash
# Registers the Debezium Postgres connector with the local Kafka Connect cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONNECT_URL="${KAFKA_CONNECT_URL:-http://localhost:8083}"
CONNECTOR_CONFIG="${SCRIPT_DIR}/../connectors/postgres-debezium-connector.json"

"${SCRIPT_DIR}/wait-for-kafka-connect.sh"

echo "Registering connector from ${CONNECTOR_CONFIG} ..."
curl -sf -X POST \
    -H "Content-Type: application/json" \
    -d @"${CONNECTOR_CONFIG}" \
    "${CONNECT_URL}/connectors" | tee /dev/stderr > /dev/null

echo
echo "Connector status:"
curl -sf "${CONNECT_URL}/connectors/iot-postgres-connector/status"
echo
