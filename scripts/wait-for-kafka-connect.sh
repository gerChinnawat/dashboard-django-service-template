#!/usr/bin/env bash
# Polls the Kafka Connect REST API until it responds, or times out.
set -euo pipefail

CONNECT_URL="${KAFKA_CONNECT_URL:-http://localhost:8083}"
MAX_ATTEMPTS=30
ATTEMPT=0

echo "Waiting for Kafka Connect at ${CONNECT_URL} ..."

until curl -sf "${CONNECT_URL}/connectors" > /dev/null 2>&1; do
    ATTEMPT=$((ATTEMPT + 1))
    if [ "${ATTEMPT}" -ge "${MAX_ATTEMPTS}" ]; then
        echo "Kafka Connect did not become ready after ${MAX_ATTEMPTS} attempts." >&2
        exit 1
    fi
    sleep 2
done

echo "Kafka Connect is ready."
