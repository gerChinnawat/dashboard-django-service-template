# Enterprise IoT Analytics Dashboard

A local dev stack for the CDC → Kafka → Snowflake → Django architecture described in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): Postgres (OLTP) → Debezium (CDC) → Kafka → Snowflake (OLAP, aggregated) → Django REST API → dashboard.

See also: [`docs/CODING_GUIDELINES.md`](docs/CODING_GUIDELINES.md), [`docs/TESTING_GUIDELINES.md`](docs/TESTING_GUIDELINES.md), [`docs/LAYER_GUIDELINES.md`](docs/LAYER_GUIDELINES.md), [`docs/NAMING_CONVENTIONS.md`](docs/NAMING_CONVENTIONS.md), [`docs/DATA_PRECISION_GUIDELINES.md`](docs/DATA_PRECISION_GUIDELINES.md), [`docs/SECURITY.md`](docs/SECURITY.md), [`docs/GIT_GUIDE.md`](docs/GIT_GUIDE.md).

---

## Getting started (first time)

New to this repo? Do these in order — each links to the full section below if you get stuck.

1. [ ] Install Python **3.12** (this repo pins it in `.python-version` — avoid 3.13+, see [Prerequisites](#prerequisites)) and Docker.
2. [ ] `docker compose up -d` — starts Postgres/Kafka/Debezium/Redis. See [1. Start the local stack](#1-start-the-local-stack).
3. [ ] `./scripts/register-debezium-connector.sh` — one-time CDC wiring. See [2. Register the Debezium connector](#2-register-the-debezium-connector).
4. [ ] Set up `django_app/venv` and run the API. See [3. Run the Django API](#3-run-the-django-api). You do **not** need a Snowflake account — the API runs against a mock client by default.
5. [ ] Run the unit tests (`cd django_app && pytest`) — these need no infra at all and are the fastest way to confirm your environment works. See [Running tests](#running-tests).
6. [ ] Before your first commit: skim [`docs/CODING_GUIDELINES.md`](docs/CODING_GUIDELINES.md) and [`docs/LAYER_GUIDELINES.md`](docs/LAYER_GUIDELINES.md) (where new code belongs) and run `make lint` (see [Formatting & linting](#formatting--linting)).

If step 4 fails with a `clang`/Xcode error while installing dependencies, it's almost always a Python-version mismatch (see [Prerequisites](#prerequisites)), not a problem with the code — recreate the venv with `python3.12` specifically.

---

## Prerequisites

- Docker + Docker Compose
- Python 3.11–3.12 (pinned to `3.12` in `.python-version` — avoid 3.13+ for now, `cffi`/`snowflake-connector-python` may not ship prebuilt wheels yet, which forces a source build and fails if your system `clang`/Xcode setup is broken). If you use `pyenv`, `pyenv install 3.12 && pyenv local 3.12` picks up `.python-version` automatically.
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

Unit tests run inside `django_app/venv` (the app's own env). Integration/e2e tests run against the repo root's `requirements-dev.txt`, which has no Django dependency — keep them in a separate venv at the repo root rather than reusing `django_app/venv`, so each layer only installs what it actually needs (see `docs/TESTING_GUIDELINES.md`).

```bash
# Unit tests (no infra required — uses SQLite + a mock Snowflake client)
cd django_app
python3.12 -m venv venv && source venv/bin/activate   # if not already created
pip install -r requirements-dev.txt
pytest

# Integration tests (requires steps 1-2 above) — separate venv at repo root
cd ..
python3.12 -m venv venv && source venv/bin/activate   # if not already created
pip install -r requirements-dev.txt
pytest -m integration

# End-to-end tests (requires steps 1-3 above, i.e. `manage.py runserver` also running)
pytest -m e2e
```

See `docs/TESTING_GUIDELINES.md` for what belongs in each layer.

## Formatting & linting

```bash
pip install -r requirements-format.txt
make format   # apply black + ruff --fix
make lint     # check only (what CI should run)
```

`make lint` also enforces naming conventions (ruff's `N` rule set) — see [`docs/NAMING_CONVENTIONS.md`](docs/NAMING_CONVENTIONS.md). Unlike formatting, naming violations aren't auto-fixed by `make format`; a failing `N` rule needs a manual rename since a tool can't safely guess every call site.

Optionally enable as a pre-commit hook: `pre-commit install`.

---

## Reference SQL

`sql/snowflake_aggregation.sql` is not run by anything in this local stack — it's the DDL/task definition to apply manually against a real Snowflake account (`telemetry_raw` → 5-minute aggregation → `device_summary_5m`).

## Tearing down

```bash
docker compose down -v   # -v also removes the Postgres data volume
```
