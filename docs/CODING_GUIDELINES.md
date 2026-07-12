# Coding Guidelines

[← Back to README](../README.md)

Conventions for this repo, grounded in the architecture in [`ARCHITECTURE.md`](ARCHITECTURE.md): Postgres (OLTP) → Debezium → Kafka → Snowflake (OLAP) → Django REST API. Examples below are taken from or modeled on the actual code in `django_app/`.

---

## 0. Formatting is automated — don't hand-format or bikeshed style in review

This repo uses **black** (formatting) and **ruff** (linting + import sorting), configured in `pyproject.toml`. Style should never be a manual/review-time concern.

```bash
pip install -r requirements-format.txt

make format        # apply black + ruff --fix
make lint          # check only, no changes (what CI runs)
```

Optionally wire it in as a git hook so it runs automatically on every commit:

```bash
pre-commit install
```

**Good:** run `make format` before committing, let ruff/black settle import order, line length, quote style, etc.

**Bad:** manually reflowing lines, arguing in review about tabs/quotes/import order, or hand-editing something ruff/black would have auto-fixed — it wastes review time on something a tool already resolves deterministically.

Why: consistent formatting across a repo this size only holds up if it's mechanical. Manual formatting drifts the moment a second contributor has different editor settings.

---

## 1. Django never queries Snowflake directly in views — go through the client

Views should call `core.snowflake_client.get_snowflake_client()`, never build Snowflake SQL or open a connection inline. This keeps the mock/real switch in one place and keeps views testable without credentials.

**Good** (`dashboard/views.py`):

```python
class SummaryView(APIView):
    def get(self, request):
        rows = get_snowflake_client().get_summary()
        return Response(SummaryRowSerializer(rows, many=True).data)
```

**Bad:**

```python
class SummaryView(APIView):
    def get(self, request):
        import snowflake.connector
        conn = snowflake.connector.connect(account=..., user=..., password=...)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM device_summary_5m ORDER BY window_start DESC")
        return Response(cursor.fetchall())
```

Why: connection setup scattered across views can't be mocked for local dev, leaks credentials handling into unrelated code, and means every view reimplements connection/error handling.

---

## 2. Operational models are reference-only and `managed = False`

Postgres is the operational system of record. Django's `telemetry` app mirrors that schema for read access, but must never migrate or write to it — the operational app owns writes, CDC/Kafka/Snowflake own the read path for analytics.

**Good** (`telemetry/models.py`):

```python
class Device(models.Model):
    device_code = models.CharField(max_length=64, unique=True)
    ...

    class Meta:
        managed = False
        db_table = "devices"
```

**Bad:**

```python
class Device(models.Model):
    device_code = models.CharField(max_length=64, unique=True)
    ...
    # no Meta.managed = False — `manage.py migrate` will try to create/alter
    # this table, fighting with the operational app and Debezium's schema.
```

Why: if Django "owns" a migration for a table Debezium is capturing, a `migrate` run can silently diverge the schema Debezium expects, breaking CDC.

---

## 3. Don't add real business logic to the mock Snowflake client — only shape-matched fixtures

`MockSnowflakeClient` exists so the API is runnable with zero external dependencies. It should return static/deterministic data shaped like the real tables — not branch on request parameters trying to simulate real aggregation behavior.

**Good** (`core/snowflake_client.py`):

```python
class MockSnowflakeClient(BaseSnowflakeClient):
    def get_site_summary(self, site_id):
        return [row for row in self._fixture_rows() if row["site"] == site_id]
```

**Bad:**

```python
class MockSnowflakeClient(BaseSnowflakeClient):
    def get_site_summary(self, site_id):
        # Reimplementing aggregation logic here means the mock can drift from
        # what Snowflake actually computes, and every "what if" case has to be
        # hand-coded.
        if site_id == "A" and datetime.now().hour < 12:
            return [...]
        elif site_id == "A":
            return [...]
        ...
```

Why: the mock's job is to unblock local development against the real API shape, not to simulate Snowflake's aggregation semantics — that logic belongs in `sql/snowflake_aggregation.sql`, reviewed against the real warehouse.

---

## 4. Config comes from environment variables via Django settings, never hardcoded

Connection details (Postgres, Kafka, Snowflake) belong in `.env` / `settings.py`, read once, and referenced through `settings.SNOWFLAKE` / `settings.DATABASES`. Never inline credentials or hosts in views, scripts, or client code.

**Good** (`config/settings.py` + `core/snowflake_client.py`):

```python
SNOWFLAKE = {
    "ACCOUNT": os.environ.get("SNOWFLAKE_ACCOUNT", ""),
    ...
}

def get_snowflake_client():
    config = settings.SNOWFLAKE
    if config.get("ACCOUNT"):
        return SnowflakeClient(config)
    return MockSnowflakeClient()
```

**Bad:**

```python
def get_snowflake_client():
    return SnowflakeClient(account="acme-corp", user="dashboard_svc", password="hunter2")
```

Why: hardcoded credentials can't differ between local/staging/prod, get committed to git history, and bypass the mock-fallback pattern entirely.

---

## 5. Serializers define the API contract explicitly — don't return raw dicts/rows

Every endpoint response should pass through a `serializers.Serializer`, even for read-only data from Snowflake. This keeps field names, types, and null-handling consistent and documented in one place.

**Good** (`dashboard/serializers.py` + `views.py`):

```python
class SummaryRowSerializer(serializers.Serializer):
    window_start = serializers.DateTimeField()
    site = serializers.CharField()
    avg_temp = serializers.FloatField()
    max_temp = serializers.FloatField()
    alert_count = serializers.IntegerField()

# view:
return Response(SummaryRowSerializer(rows, many=True).data)
```

**Bad:**

```python
# view:
rows = get_snowflake_client().get_summary()
return Response(rows)  # raw dicts straight from the client, whatever shape they happen to be
```

Why: without a serializer, a column rename in Snowflake (or in the mock fixture) silently changes the API's JSON shape with no single place documenting what consumers can rely on.

Note: serializers define shape and types, **not display precision** — don't add `round()` here or in views. The API returns unrounded aggregate values; rounding happens only at display time in the frontend. See [`DATA_PRECISION_GUIDELINES.md`](DATA_PRECISION_GUIDELINES.md).

---

## 6. Infra config (Debezium connector, docker-compose) stays declarative and out of application code

Connector definitions live in `connectors/*.json` and are registered via `scripts/register-debezium-connector.sh`, not constructed or POSTed from Python/Django code.

**Good** (`scripts/register-debezium-connector.sh`):

```bash
curl -sf -X POST -H "Content-Type: application/json" \
    -d @"${CONNECTOR_CONFIG}" \
    "${CONNECT_URL}/connectors"
```

**Bad:**

```python
# somewhere in django_app/
import requests
requests.post("http://kafka-connect:8083/connectors", json={
    "name": "iot-postgres-connector",
    "config": {"connector.class": "io.debezium.connector.postgresql.PostgresConnector", ...},
})
```

Why: connector registration is a one-time ops step tied to the infra lifecycle, not application runtime behavior — mixing it into Django code makes it run (and fail) at the wrong time and hides infra changes from anyone reviewing `connectors/`.
