# Layer Guidelines

[← Back to README](../README.md)

A guide for adding a new module to `django_app/` without guessing where code should live. Written for anyone new to this codebase — read [`CODING_GUIDELINES.md`](CODING_GUIDELINES.md) and [`TESTING_GUIDELINES.md`](TESTING_GUIDELINES.md) alongside this, they're not repeated here.

---

## The five layers

A request flows through these layers in order. Data only ever flows **down** through a request (view → service → repository → database/Snowflake) and **up** through the response (repository → service → view → serializer → JSON). A layer should never reach *past* the one directly below it.

```
URL (urls.py)
  → View (views.py)              -- HTTP in, HTTP out. No business logic, no SQL.
      → Service (services.py)    -- business logic, orchestrates 1+ repositories.
          → Repository            -- the only place that talks to a database/API.
              → Model / client    -- Django ORM model, or an external client (Snowflake).
      → Serializer (serializers.py) -- shapes the response. Called by the view, not the service.
  → Util (utils.py)              -- pure helper functions, callable from any layer above.
```

| Layer | File | Knows about | Must NOT know about |
|---|---|---|---|
| **View** | `<app>/views.py` | HTTP request/response, which service/repository to call, which serializer to use | SQL, ORM querysets, Snowflake, business rules |
| **Service** | `<app>/services.py` | Business rules, which repositories to combine | `request`/`Response` objects, serializers, HTTP status codes |
| **Repository** | `<app>/repository.py` or `core/snowflake_client.py` | How to fetch/persist one kind of data (ORM queryset, Snowflake SQL) | Business rules, other repositories, HTTP |
| **Model** | `<app>/models.py` | Table shape (`managed = False` — see `CODING_GUIDELINES.md` #2) | Everything else — models are data shape only, no query logic |
| **Serializer (DTO)** | `<app>/serializers.py` | The external API contract — field names, types, nullability | Where the data came from (Postgres, Snowflake, a service's internal dict shape), business rules |
| **Util** | `core/utils.py` (or `<app>/utils.py` for app-specific helpers) | Pure input → output logic, no I/O | Django settings, the database, HTTP, other layers |

Not every endpoint needs all five. `dashboard/views.py` today calls the Snowflake repository (`core/snowflake_client.py`) directly with no service layer, because there's nothing to orchestrate — one repository call, one serializer. **Add a service only once a view would otherwise contain business logic or call more than one repository.** Don't add an empty pass-through service "for consistency" — see `CLAUDE.md`'s instruction against premature abstraction.

---

## What belongs in each layer

### Model

Read-only shape of a table. In this repo, operational models mirror Postgres (`telemetry/models.py`) and are always `managed = False` (`CODING_GUIDELINES.md` #2) — Django never migrates or writes to them. A model has fields and `Meta`, nothing else. No query methods, no business logic, no `save()` overrides.

### Repository

The **only** place allowed to write a Django ORM queryset or Snowflake SQL. Two examples already exist in this codebase:

- `core/snowflake_client.py` — `SnowflakeClient` / `MockSnowflakeClient`, one method per query, e.g. `get_summary()`, `get_site_summary(site_id)`.
- For Postgres reads, a repository is a plain function wrapping the ORM (see the worked example below) — it doesn't need a class if there's no mock/real split to manage.

A repository returns plain data (dicts, model instances, lists) — never a `Response`, never a serializer.

### Service

Orchestrates repositories and applies business rules that don't belong in a view or a repository — e.g. combining a Postgres lookup with a Snowflake query, computing a derived status, enforcing a domain rule ("a device with no telemetry in 24h is offline"). A service function takes plain arguments and returns plain data (dict/dataclass), same as a repository. It never imports `rest_framework`.

### View

As thin as possible: parse the request, call one service or repository, pass the result through a serializer, return `Response(...)`. See `CODING_GUIDELINES.md` #1 and #5 — this is already an enforced convention for the Snowflake client and serializers.

### Serializer (DTO)

Think of a `serializers.Serializer` subclass as a **Data Transfer Object**: a fixed, explicit shape whose only job is to move data across the view/HTTP boundary. It is not a model, not a database table, and — importantly in this codebase — often has no ORM model behind it at all, since most dashboard data is plain dicts from Snowflake or a service. That's fine; DRF's `Serializer` (as opposed to `ModelSerializer`) is designed for exactly this: declare fields by hand, feed it any object/dict that has matching attributes or keys.

**Why a DTO layer, instead of returning the dict a repository/service already built:**

- **Decouples the wire format from internal representation.** A repository or Snowflake column can be renamed, restructured, or recomputed without the API contract moving — the serializer is the one place that translates. Without it, a rename in `sql/snowflake_aggregation.sql` or a mock fixture silently changes what every API consumer receives.
- **Is the single source of truth for what the API promises.** Anyone can read `serializers.py` and know the exact contract — field names, types, nullability — without tracing through a repository or Snowflake schema.
- **Coerces and validates at the boundary.** `serializers.FloatField()` on a `Decimal` from Snowflake, `serializers.DateTimeField()` on a raw timestamp — the serializer normalizes types once, here, instead of every caller having to know what shape the underlying data happens to be in.
- **Can hide internal-only fields.** A service's return dict is free to carry extra fields useful for logging or a future feature; the serializer only emits what's declared, so nothing leaks into the API by accident.

**Good** (`dashboard/serializers.py` + `views.py` — DTO shape is independent of the mock/real Snowflake client's row shape):

```python
class SummaryRowSerializer(serializers.Serializer):
    window_start = serializers.DateTimeField()
    site = serializers.CharField()
    avg_temp = serializers.FloatField()
    max_temp = serializers.FloatField()
    alert_count = serializers.IntegerField()

# view: the serializer is the only thing that decides what goes over the wire
rows = get_snowflake_client().get_summary()
return Response(SummaryRowSerializer(rows, many=True).data)
```

**Bad** (view returns whatever shape the repository happens to produce):

```python
rows = get_snowflake_client().get_summary()
return Response(rows)  # if Snowflake adds an internal `_debug_query_id` column
                        # tomorrow, it ships straight to every API consumer
```

**This also applies to input, not just output.** If a future endpoint accepts a request body or query params beyond a simple path parameter, define an input serializer the same way (`serializers.Serializer` with `is_valid()`/`validated_data`) rather than reading `request.data` directly in the view or service — same DTO principle, applied to the direction data flows in.

**In the worked example below**, `DeviceHealthSerializer` is deliberately a different shape than the dict `get_device_health()` returns internally — the service is free to add, say, an internal `_raw_summary_row` key for debugging without it ever reaching the response, because the serializer only reads the five fields it declares.

### Util

Pure functions: given the same input, always the same output, no side effects, no imports from Django/DB/network. Put them in `core/utils.py` if they're shared across apps, or `<app>/utils.py` if specific to one app. Utils are the easiest thing in the codebase to unit test — no mocking required — so push logic here whenever it doesn't need a repository or request context.

---

## Worked example: adding a "device health" endpoint

Goal: `GET /dashboard/device/<device_code>/health` returns whether a device is `ok`, `warning`, or `critical`, based on its Postgres registration (which site it's in) and that site's latest Snowflake summary.

This touches every layer, because it genuinely needs to: look up a device in Postgres (repository #1), pull that site's summary from Snowflake (repository #2 — already exists), classify the result (pure logic → util), and combine both lookups (service). A single view calling a single repository would not be enough here, which is exactly the signal to add a service.

### 1. Util — pure classification logic

`core/utils.py` (new file):

```python
def classify_temperature(avg_temp, max_temp):
    """Pure classification, no I/O -- trivially unit-testable in isolation."""
    if max_temp >= 32:
        return "critical"
    if avg_temp >= 28:
        return "warning"
    return "ok"
```

### 2. Repository — Postgres device lookup

`telemetry/repository.py` (new file):

```python
from .models import Device


class DeviceNotFound(Exception):
    pass


def get_device_by_code(device_code):
    """The only place that queries the Device model directly."""
    try:
        return Device.objects.get(device_code=device_code)
    except Device.DoesNotExist:
        raise DeviceNotFound(device_code) from None
```

(The Snowflake side already has its repository: `get_snowflake_client().get_site_summary(site_id)` in `core/snowflake_client.py` — no changes needed there.)

### 3. Service — orchestrates both repositories + the util

`dashboard/services.py` (new file):

```python
from core.snowflake_client import get_snowflake_client
from core.utils import classify_temperature
from telemetry.repository import DeviceNotFound, get_device_by_code


class DeviceNotFoundError(Exception):
    pass


def get_device_health(device_code):
    try:
        device = get_device_by_code(device_code)
    except DeviceNotFound:
        raise DeviceNotFoundError(device_code) from None

    summary_rows = get_snowflake_client().get_site_summary(device.site)
    if not summary_rows:
        return {"device_code": device_code, "site": device.site, "status": "ok", "avg_temp": None, "max_temp": None}

    latest = summary_rows[0]
    status = classify_temperature(latest["avg_temp"], latest["max_temp"])
    return {
        "device_code": device_code,
        "site": device.site,
        "status": status,
        "avg_temp": latest["avg_temp"],
        "max_temp": latest["max_temp"],
    }
```

Note: `services.py` never imports `rest_framework` — it's plain Python, callable from a view, a management command, or a test with no HTTP involved.

### 4. Serializer — the response contract

`dashboard/serializers.py` (add to the existing file):

```python
class DeviceHealthSerializer(serializers.Serializer):
    device_code = serializers.CharField()
    site = serializers.CharField()
    status = serializers.ChoiceField(choices=["ok", "warning", "critical"])
    avg_temp = serializers.FloatField(allow_null=True)
    max_temp = serializers.FloatField(allow_null=True)
```

### 5. View — thin HTTP glue

`dashboard/views.py` (add to the existing file):

```python
from .services import DeviceNotFoundError, get_device_health


class DeviceHealthView(APIView):
    """GET /dashboard/device/{device_code}/health -- current status derived
    from the device's site summary."""

    def get(self, request, device_code):
        try:
            health = get_device_health(device_code)
        except DeviceNotFoundError:
            return Response({"detail": "device not found"}, status=404)
        logger.info("dashboard.device_health served", extra={"device_code": device_code})
        return Response(DeviceHealthSerializer(health).data)
```

### 6. URL

`dashboard/urls.py`:

```python
path("device/<str:device_code>/health", views.DeviceHealthView.as_view(), name="dashboard-device-health"),
```

### 7. Tests — one per layer, per `TESTING_GUIDELINES.md`

- **Util**: call `classify_temperature(28, 30)` directly, assert `"warning"` — no mocking needed.
- **Repository**: `telemetry/tests/test_repository.py` — hit the SQLite test DB (`Device.objects.create(...)` then `get_device_by_code(...)`), assert `DeviceNotFound` for an unknown code.
- **Service**: `dashboard/tests/test_services.py` — patch `get_device_by_code` and `get_snowflake_client` (same pattern as `MOCK_CLIENT_PATCH` in `dashboard/tests/test_views.py`), assert the returned dict's `status` for a given fixture.
- **View**: `dashboard/tests/test_views.py` — patch `dashboard.views.get_device_health`, hit `/dashboard/device/dev-001/health` via the Django test client, assert the JSON shape matches the serializer contract.

Each layer's test only mocks the layer directly below it — the view test doesn't need to know Snowflake or Postgres exist at all.

---

## Quick checklist when adding a module

1. Does this need a **repository**? Only if it queries a database or external API. One repository per data source, one method per query — don't let a repository grow into a dumping ground for unrelated queries.
2. Does this need a **service**? Only if a view would otherwise contain business logic or call more than one repository. If it's a single repository call passed straight to a serializer, skip the service — call the repository from the view, like `SummaryView` does today.
3. Is any part of the logic pure (no I/O)? Pull it into **utils** — it's the cheapest thing in the stack to test and reuse.
4. Does the response go through a **serializer**? Always, per `CODING_GUIDELINES.md` #5 — never return a raw dict/queryset from a view.
5. Did you add a test at the layer where the logic actually lives, not just an end-to-end view test? An end-to-end test alone means a util/service bug only surfaces through an HTTP assertion, which makes failures harder to localize.
