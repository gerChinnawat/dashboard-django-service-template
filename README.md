# Enterprise IoT Analytics Dashboard

A local dev stack for the CDC → Kafka → Snowflake → Django architecture described in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): Postgres (OLTP) → Debezium (CDC) → Kafka → Snowflake (OLAP, aggregated) → Django REST API → dashboard.

See also: [`docs/CODING_GUIDELINES.md`](docs/CODING_GUIDELINES.md), [`docs/TESTING_GUIDELINES.md`](docs/TESTING_GUIDELINES.md), [`docs/SECURITY.md`](docs/SECURITY.md), [`docs/GIT_GUIDE.md`](docs/GIT_GUIDE.md).

---

## Prerequisites

- Docker + Docker Compose
- Python 3.11–3.12 (avoid 3.13+ for now — `cffi`/`snowflake-connector-python` may not ship prebuilt wheels yet, which forces a source build and fails if your system `clang`/Xcode setup is broken)
- `psql` and `curl` (for manual verification steps below)

---

## 1. Start the local stack

Brings up Postgres (CDC-enabled), Zookeeper, Kafka, Kafka Connect (Debezium), and Redis (dashboard response cache):

```bash
docker compose up -d
```

Postgres is seeded from `sql/init_operational_schema.sql` on first start (creates `devices`, `telemetry`, `alerts`, and the CDC publication).

## 2. Register the Debezium connector

This is the one manual step after the stack is up — it tells Kafka Connect to start streaming Postgres changes into Kafka:

```bash
./scripts/register-debezium-connector.sh
```

Verify it's running:

```bash
curl localhost:8083/connectors/iot-postgres-connector/status
```

## 3. Run the Django API

```bash
cd django_app
python3.12 -m venv venv && source venv/bin/activate
cp ../.env.example ../.env   # adjust if your Postgres/Kafka ports differ
pip install -r requirements.txt
python manage.py runserver
```

No Snowflake account? Leave `SNOWFLAKE_ACCOUNT` blank in `.env` — the API automatically falls back to a mock Snowflake client with fixture data shaped like the real summary tables (see `core/snowflake_client.py`).

Try the endpoints:

```bash
curl localhost:8000/dashboard/summary
curl localhost:8000/dashboard/devices
curl localhost:8000/dashboard/site/A
curl localhost:8000/dashboard/alerts
```

## 4. Confirm CDC is flowing (optional)

Insert a row and watch it land on Kafka:

```bash
psql -h localhost -U iot_app -d iot_operational \
  -c "INSERT INTO devices (device_code, site, device_type) VALUES ('dev-001', 'A', 'sensor');"

docker exec -it iot-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 --topic iot.public.devices --from-beginning --max-messages 1
```

---

## Caching

Dashboard endpoints (`/dashboard/summary`, `/devices`, `/site/<id>`, `/alerts`) cache their full response in Redis for `DASHBOARD_CACHE_TTL_SECONDS` (default 60s, see `.env`) — the underlying `device_summary_5m` rollup only changes every 5 minutes, so this cuts repeated Snowflake queries without serving stale data for long. Caching is keyed by request path via Django's `cache_page`; see `dashboard/views.py`. Unit tests use a `DummyCache` backend (`config/settings_test.py`) so no Redis is required and each test hits the (mocked) Snowflake client directly.

## Logging & metrics

The Django API logs structured JSON to stdout (`config/settings.py` `LOGGING`) — set `DJANGO_LOG_LEVEL` in `.env` to change verbosity. Prometheus-format metrics (request latency, DB query count, response codes) are exposed at:

```bash
curl localhost:8000/metrics
```

Point a Prometheus scraper at that endpoint, or query it directly for request-latency histograms and per-view hit counts. See `docs/SECURITY.md` #6 before exposing `/metrics` beyond localhost.

---

## Running tests

```bash
# Unit tests (no infra required — uses SQLite + a mock Snowflake client)
cd django_app
pip install -r requirements-dev.txt
pytest

# Integration tests (requires steps 1-2 above)
pip install -r ../requirements-dev.txt   # from repo root
cd ..
pytest -m integration

# End-to-end tests (requires steps 1-3 above)
pytest -m e2e
```

See `docs/TESTING_GUIDELINES.md` for what belongs in each layer.

## Formatting & linting

```bash
pip install -r requirements-format.txt
make format   # apply black + ruff --fix
make lint     # check only (what CI should run)
```

Optionally enable as a pre-commit hook: `pre-commit install`.

---

## Reference SQL

`sql/snowflake_aggregation.sql` is not run by anything in this local stack — it's the DDL/task definition to apply manually against a real Snowflake account (`telemetry_raw` → 5-minute aggregation → `device_summary_5m`).

## Tearing down

```bash
docker compose down -v   # -v also removes the Postgres data volume
```
