# Testing Guidelines

[← Back to README](../README.md)

Conventions for testing this repo, grounded in the architecture in [`ARCHITECTURE.md`](ARCHITECTURE.md). The core principle: tests must run with **no Postgres, no Kafka, no Snowflake account** — everything downstream of Django is either mocked or swapped for an in-memory equivalent.

---

## 1. Never hit a real Snowflake account in tests — inject the mock client

`MockSnowflakeClient` already exists for exactly this. Tests should either call it directly or monkeypatch `get_snowflake_client` to return a `MockSnowflakeClient` (or a purpose-built fake), never rely on real credentials being present in CI.

**Good** (`dashboard/tests/test_views.py`):

```python
from unittest.mock import patch
from core.snowflake_client import MockSnowflakeClient

class SummaryViewTests(TestCase):
    @patch("dashboard.views.get_snowflake_client", return_value=MockSnowflakeClient())
    def test_summary_returns_rows_shaped_like_the_readme_table(self, mock_get_client):
        response = self.client.get("/dashboard/summary")
        self.assertEqual(response.status_code, 200)
        self.assertIn("avg_temp", response.json()[0])
```

**Bad:**

```python
class SummaryViewTests(TestCase):
    def test_summary(self):
        # Relies on real SNOWFLAKE_ACCOUNT/USER/PASSWORD env vars being set
        # wherever this test runs. Fails or hangs in CI, and can rack up
        # warehouse compute cost just to run a unit test.
        response = self.client.get("/dashboard/summary")
        self.assertEqual(response.status_code, 200)
```

Why: `get_snowflake_client()` already falls back to the mock when `SNOWFLAKE_ACCOUNT` is unset (`core/snowflake_client.py`), but a test env that happens to have real credentials configured (e.g. a shared `.env`) would silently start hitting production Snowflake from unit tests.

---

## 2. Test the Django API layer with `django.test.Client`, not by spinning up `runserver`

Use DRF's/Django's test client against `urls.py`, not manual HTTP requests against a locally running server. This is faster, deterministic, and doesn't depend on ports being free.

**Good:**

```python
class DashboardEndpointsTests(TestCase):
    def test_all_endpoints_return_200(self):
        for url in ["/dashboard/summary", "/dashboard/devices", "/dashboard/alerts"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
```

**Bad:**

```python
def test_all_endpoints_return_200():
    import subprocess, time, requests
    subprocess.Popen(["python", "manage.py", "runserver", "8123"])
    time.sleep(3)  # hope the server is up by now
    assert requests.get("http://localhost:8123/dashboard/summary").status_code == 200
```

Why: the subprocess approach is flaky (arbitrary sleep, port collisions in parallel CI), slow, and leaks a server process if the test fails before cleanup.

---

## 3. Don't point `telemetry` model tests at a real Postgres/Debezium stack

`telemetry` models are `managed = False` reference mirrors of the operational schema (see `docs/CODING_GUIDELINES.md` #2). Tests that need row-level behavior should use Django's test database (SQLite is fine) with `@pytest.mark.django_db` / `TestCase`, not the docker-compose Postgres+Kafka+Debezium stack.

**Good:**

```python
class DeviceModelTests(TestCase):
    def test_str_repr_uses_device_code(self):
        device = Device.objects.create(device_code="dev-001", site="A", device_type="sensor", ...)
        self.assertEqual(str(device), "dev-001")
```

**Bad:**

```python
class DeviceModelTests(TestCase):
    def setUp(self):
        # requires `docker compose up` and a registered Debezium connector
        # to even construct a Device row
        subprocess.run(["docker", "compose", "up", "-d"])
        subprocess.run(["./scripts/register-debezium-connector.sh"])
```

Why: model unit tests should verify Python-level behavior (field defaults, `__str__`, validation), not the CDC pipeline — that belongs in a separate integration/smoke test (see #5) that's allowed to be slower and infra-dependent.

---

## 4. Assert on the serializer contract, not on raw Snowflake/mock row shape

Because every endpoint response goes through a `Serializer` (`docs/CODING_GUIDELINES.md` #5), tests should assert on the serialized JSON shape the client actually receives — not reach into `MockSnowflakeClient` internals and compare dicts directly.

**Good:**

```python
def test_summary_row_has_expected_fields(self):
    response = self.client.get("/dashboard/summary")
    row = response.json()[0]
    self.assertEqual(
        set(row.keys()),
        {"window_start", "site", "avg_temp", "max_temp", "alert_count"},
    )
```

**Bad:**

```python
def test_summary_row_has_expected_fields(self):
    rows = MockSnowflakeClient().get_summary()
    self.assertEqual(set(rows[0].keys()), {"window_start", "site", "avg_temp", "max_temp", "alert_count"})
    # never actually calls the view/serializer, so a bug in SummaryRowSerializer
    # (typo'd field name, wrong type) would pass this test while breaking the real API
```

Why: the point of the serializer layer is the API contract; a test that bypasses it can't catch serializer regressions.

---

## 5. Infra (docker-compose, Debezium connector, Snowflake SQL) gets a smoke test, not a unit test

`docker-compose.yml`, `connectors/*.json`, and `sql/*.sql` are ops artifacts, not application code — don't try to unit-test them with mocked Python. Instead, keep one documented manual/CI smoke test path (matching the verification steps in the project plan) and mark it explicitly as an integration test that requires the full stack.

**Good** (`tests/integration/test_cdc_smoke.py`, run only in a dedicated CI job or manually):

```python
@pytest.mark.integration  # excluded from the default test run
def test_insert_produces_cdc_event_on_kafka_topic():
    """Requires `docker compose up -d` + registered connector. See README verification steps."""
    ...
```

**Bad:**

```python
# in the regular unit test suite, run on every `pytest`
def test_debezium_connector_json_is_valid():
    config = json.load(open("connectors/postgres-debezium-connector.json"))
    assert config["config"]["connector.class"] == "io.debezium.connector.postgresql.PostgresConnector"
    # gives false confidence: valid JSON with the right class name doesn't mean
    # the connector actually registers or produces events correctly
```

Why: unit-testing static config for schema correctness is cheap but tests the wrong thing — the failure mode that matters (connector fails to register, publication misconfigured, topic naming mismatch) only shows up against the real stack, so pretending a JSON assertion covers that is worse than not testing it and just documenting the manual smoke test.

---

## Summary

| Layer | Test with | Never |
|---|---|---|
| `dashboard` views | `django.test.Client` + mocked `get_snowflake_client` | real Snowflake creds, `runserver` + `requests` |
| `telemetry` models | Django test DB (`TestCase`) | real Postgres/Debezium stack |
| Serializers | assert on `response.json()` shape | assert on raw client/mock dicts |
| `connectors/`, `docker-compose.yml`, `sql/` | one marked integration/smoke test against the real stack | unit tests that only check static file contents |
