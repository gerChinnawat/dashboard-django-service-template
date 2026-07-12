# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local dev implementation of an IoT analytics pipeline: `Postgres (OLTP) → Debezium (CDC) → Kafka → Snowflake (OLAP, aggregated) → Django REST API → dashboard`. Full architecture rationale is in `docs/ARCHITECTURE.md`. This repo currently implements the docker-compose stack + Django skeleton; there is no frontend yet.

Read `docs/CODING_GUIDELINES.md` and `docs/TESTING_GUIDELINES.md` before changing code — both have concrete good/bad examples pulled from this codebase and are treated as binding conventions, not suggestions. `docs/LAYER_GUIDELINES.md` explains where new code belongs (view/service/repository/model/util) with a worked example — read it before adding a new module. `docs/NAMING_CONVENTIONS.md` covers what to call things; naming is lint-enforced (ruff's `N` rule set, see `pyproject.toml`) but not auto-fixed by `make format`.

## Commands

All Python commands assume a venv with the relevant requirements file installed.

```bash
# Start the infra stack (Postgres + Zookeeper + Kafka + Kafka Connect/Debezium)
docker compose up -d
./scripts/register-debezium-connector.sh   # one-time, registers connectors/postgres-debezium-connector.json

# Run the Django API (from django_app/)
cd django_app && pip install -r requirements.txt && python manage.py runserver

# Unit tests (django_app/, no infra needed — SQLite + mock Snowflake client)
cd django_app && pip install -r requirements-dev.txt && pytest
pytest dashboard/tests/test_views.py::DashboardEndpointsTests::test_summary_row_matches_serializer_contract  # single test

# Integration tests (repo root, requires docker-compose stack running — step 1-2 above)
pip install -r requirements-dev.txt && pytest -m integration

# E2E tests (repo root, requires stack + `manage.py runserver` also running)
pytest -m e2e

# Format & lint (repo root)
pip install -r requirements-format.txt
make format   # black + ruff --fix
make lint     # check only, no changes — this is what CI should run
```

Note there are **two separate `pytest.ini` files**: `django_app/pytest.ini` (Django settings wiring, for unit tests) and the root `pytest.ini` (marker-gated, for `tests/integration` and `tests/e2e`). Running bare `pytest` from the repo root deliberately collects zero tests (`addopts = -m "not integration and not e2e"`) — you must pass `-m integration` or `-m e2e` explicitly, or `cd django_app` for unit tests.

## Architecture — things that span multiple files

**Snowflake access is centralized and mock-first.** `django_app/core/snowflake_client.py` exposes `get_snowflake_client()`, which returns a real `SnowflakeClient` if `SNOWFLAKE_ACCOUNT` is set in settings, otherwise a `MockSnowflakeClient` returning fixture data shaped like the real summary tables. `dashboard/views.py` only ever calls `get_snowflake_client()` — never builds Snowflake SQL or opens a connection itself. This is why the whole API layer runs with zero external dependencies in tests and local dev.

**Django never mutates or migrates the operational schema.** `django_app/telemetry/models.py` (`Device`, `Telemetry`, `Alert`) mirrors `sql/init_operational_schema.sql` but every model has `managed = False`. Postgres is the system of record for operational data; CDC/Kafka/Snowflake own the read path. These models exist for read-only reference/typing, not for Django to own migrations against — don't add `managed = True` or write-path code here.

**The aggregation layer (`sql/snowflake_aggregation.sql`) is not executed by any app code.** It's reference DDL/TASK definitions to run manually against a real Snowflake account (`telemetry_raw` → 5-min rollup via STREAM+TASK → `device_summary_5m`, which `SnowflakeClient` queries). Don't expect a docker-compose service or Python job to run this — there isn't one, by design (Snowflake can't run locally).

**Dashboard API has no authentication yet.** `REST_FRAMEWORK` in `config/settings.py` sets empty auth classes and `AllowAny` permissions, and `django.contrib.auth`/`contenttypes` are deliberately **not** in `INSTALLED_APPS` (adding a DRF default authenticator back in will immediately break, since `UNAUTHENTICATED_USER` is set to `None` specifically to avoid importing `django.contrib.auth.models`). See `docs/SECURITY.md` for the full list of what's out of scope for "local dev" vs. required before any real deployment — check it before hardening auth, credentials, or exposed ports.

**Serializers are the API contract, not passthrough.** Every dashboard endpoint response goes through a `rest_framework.serializers.Serializer` (`dashboard/serializers.py`), even though the data is just dicts from the Snowflake client. Tests assert on the serialized JSON shape, not on raw client/mock output — see `docs/TESTING_GUIDELINES.md` #4.

**Test layers are strictly separated by what infra they require** (see `docs/TESTING_GUIDELINES.md` for the full rationale table):
- `django_app/*/tests/` — unit tests, SQLite, mocked Snowflake client, no docker.
- `tests/integration/` — real docker-compose stack (Postgres → Debezium → Kafka), asserts CDC events land on Kafka topics.
- `tests/e2e/` — stack + running Django server, asserts the full write-to-API path.
- `tests/conftest.py` fixtures (`postgres_connection`, `kafka_connect_registered`, `django_server_reachable`) `pytest.skip()` with an actionable message when their dependency isn't reachable, rather than erroring — preserve that pattern if you add new fixtures.

**Infra config stays declarative, out of Python.** The Debezium connector definition (`connectors/postgres-debezium-connector.json`) is registered via a shell script (`scripts/register-debezium-connector.sh`) hitting the Kafka Connect REST API directly — no Django management command or Python code registers it. Keep it that way (see `docs/CODING_GUIDELINES.md` #6).

**Logging and metrics are already wired, use them rather than adding new mechanisms.** `config/settings.py` configures JSON-structured logging (`LOGGING` dict, `python-json-logger`) with dedicated `dashboard`/`core` loggers — `dashboard/views.py` and `core/snowflake_client.py` already log at `INFO` on every request/query with row counts and timing, and `core/snowflake_client.py` logs query duration and exceptions. `django-prometheus` is in `INSTALLED_APPS`/`MIDDLEWARE` (must stay first/last in `MIDDLEWARE` — see comment in `settings.py`) and the Postgres `DATABASES` engine is the `django_prometheus.db.backends.postgresql` wrapper for DB-query metrics; `/metrics` is wired in `config/urls.py`. `docs/SECURITY.md` #6 flags `/metrics` as unauthenticated by design — don't add auth to it without also updating that doc.

## Formatting

Config lives in `pyproject.toml` (black, line-length 110; ruff with E/F/I/UP/B/DJ rule sets). Don't hand-format or bikeshed style — run `make format` and let it settle import order/line length/quotes. `.pre-commit-config.yaml` wires the same checks into `pre-commit install` if you want it automatic.
