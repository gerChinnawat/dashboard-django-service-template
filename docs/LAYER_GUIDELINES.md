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

Not every endpoint needs all five. `dashboard/views.py` today calls the Snowflake repository (`core/snowflake_client.py`) directly with no service layer, because there's nothing to orchestrate — one repository call, one serializer. **Add a service only once a view would otherwise contain business logic or call more than one repository.** Don't add an empty pass-through service "for consistency" — that's premature abstraction.

---

## What belongs in each layer

### Model

Read-only shape of a table. In this repo, operational models mirror Postgres (`telemetry/models.py`) and are always `managed = False` (`CODING_GUIDELINES.md` #2) — Django never migrates or writes to them. A model has fields and `Meta`, nothing else. No query methods, no business logic, no `save()` overrides.

### Repository

The **only** place allowed to write a Django ORM queryset or Snowflake SQL. The one example that exists in this codebase today:

- `core/snowflake_client.py` — `SnowflakeClient` / `MockSnowflakeClient`, one method per query, e.g. `get_summary()`, `get_site_summary(site_id)`. It's mock-first (`docs/CODING_GUIDELINES.md` #1), which is exactly why every layer built on top of it is unit-testable with zero infra.

A repository returns plain data (dicts, model instances, lists) — never a `Response`, never a serializer.

**A caveat specific to this repo: a Postgres-backed repository (querying `telemetry/models.py`) cannot be unit tested.** Those models are `managed = False` (`CODING_GUIDELINES.md` #2) — Django never creates their tables, including in the SQLite test database, so `Device.objects.get(...)` raises `OperationalError: no such table` under `pytest` (confirm yourself: `telemetry/tests/test_models.py`'s models are only ever instantiated in memory, never queried). A repository wrapping these models is real and useful, but its test belongs in `tests/integration/` against the real docker-compose Postgres — not `django_app/*/tests/`. Keep that in mind before reaching for a Postgres repository just because the Snowflake pattern makes it look easy; it changes which test layer you're committing to.

### Service

Orchestrates repositories and applies business rules that don't belong in a view or a repository — e.g. combining a Postgres lookup with a Snowflake query, computing a derived status, enforcing a domain rule ("a device with no telemetry in 24h is offline"). A service function takes plain arguments and returns plain data (dict/dataclass), same as a repository. It never imports `rest_framework`.

### View

As thin as possible: parse the request, call one service or repository, pass the result through a serializer, return `Response(...)`. See `CODING_GUIDELINES.md` #1 and #5 — this is already an enforced convention for the Snowflake client and serializers.

### Serializer (DTO)

Think of a `serializers.Serializer` subclass as a **Data Transfer Object**: a fixed, explicit shape whose only job is to move data across the view/HTTP boundary. It is not a model, not a database table, and — importantly in this codebase — often has no ORM model behind it at all, since most dashboard data is plain dicts from Snowflake or a service. That's fine; DRF's `Serializer` (as opposed to `ModelSerializer`) is designed for exactly this: declare fields by hand, feed it any object/dict that has matching attributes or keys.

**Why a DTO layer, instead of returning the dict a repository/service already built:**

- **Decouples the wire format from internal representation.** A repository or Snowflake column can be renamed, restructured, or recomputed without the API contract moving — the serializer is the one place that translates. Without it, a rename in `sql/snowflake_aggregation.sql` or a mock fixture silently changes what every API consumer receives.
- **Is the single source of truth for what the API promises.** Anyone can read `serializers.py` and know the exact contract — field names, types, nullability — without tracing through a repository or Snowflake schema.
- **Coerces and validates at the boundary.** `serializers.FloatField()` on a `Decimal` from Snowflake, `serializers.DateTimeField()` on a raw timestamp — the serializer normalizes types once, here, instead of every caller having to know what shape the underlying data happens to be in. Coercion means type, not precision: serializers never round — see [`DATA_PRECISION_GUIDELINES.md`](DATA_PRECISION_GUIDELINES.md).
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

**In the worked example below**, `SiteHealthSerializer`'s fields happen to match `get_site_health()`'s return dict exactly — but that's incidental, not required. The service is free to add, say, an internal `_raw_summary_row` key for debugging later without it ever reaching the response, because the serializer only reads the fields it declares.

### Util

Pure functions: given the same input, always the same output, no side effects, no imports from Django/DB/network. Put them in `core/utils.py` if they're shared across apps, or `<app>/utils.py` if specific to one app. Utils are the easiest thing in the codebase to unit test — no mocking required — so push logic here whenever it doesn't need a repository or request context.

---

## Worked example: `GET /dashboard/site/<site_id>/health`

This is a real endpoint in the codebase (not hypothetical) — read the actual files alongside this section: `core/utils.py`, `dashboard/services.py`, `dashboard/serializers.py`, `dashboard/views.py`, `dashboard/urls.py`, and their tests in `core/tests/test_utils.py`, `dashboard/tests/test_services.py`, `dashboard/tests/test_views.py::SiteHealthViewTests`.

Goal: return whether a site is `ok`, `warning`, or `critical`, derived from its latest Snowflake summary row (`avg_temp`, `max_temp`).

Deliberately **not** the Postgres/`Device` cross-lookup example from an earlier version of this doc — that would require a repository over `telemetry/models.py`, which (per the caveat above) can only be tested at the integration layer, not unit tested. This example stays entirely within what `MockSnowflakeClient` already covers, which is why every layer below is unit-testable with zero infra. Combining a Postgres repository with a Snowflake repository in one service is still a legitimate pattern — just budget for an integration test, not a unit test, when you do it.

A service is warranted here even though there's only one repository call, because there's real business logic (the ok/warning/critical classification) that doesn't belong in the view — that's the "business logic" half of the "business logic OR multiple repositories" rule from the layer table above.

### 1. Util — pure classification logic (`core/utils.py`)

```python
def classify_temperature(avg_temp, max_temp):
    """Pure classification, no I/O -- trivially unit-testable in isolation."""
    if max_temp >= 32:
        return "critical"
    if avg_temp >= 28:
        return "warning"
    return "ok"
```

### 2. Service — orchestrates the existing Snowflake repository + the util (`dashboard/services.py`)

```python
from core.snowflake_client import get_snowflake_client
from core.utils import classify_temperature


def get_site_health(site_id):
    """Returns None if the site has no summary data (the view turns that
    into a 404)."""
    rows = get_snowflake_client().get_site_summary(site_id)
    if not rows:
        return None

    latest = rows[0]
    return {
        "site": site_id,
        "status": classify_temperature(latest["avg_temp"], latest["max_temp"]),
        "avg_temp": latest["avg_temp"],
        "max_temp": latest["max_temp"],
        "alert_count": latest["alert_count"],
    }
```

`services.py` never imports `rest_framework` — it's plain Python, callable from a view, a management command, or a test with no HTTP involved.

### 3. Serializer — the response contract (`dashboard/serializers.py`)

```python
class SiteHealthSerializer(serializers.Serializer):
    site = serializers.CharField()
    status = serializers.ChoiceField(choices=["ok", "warning", "critical"])
    avg_temp = serializers.FloatField()
    max_temp = serializers.FloatField()
    alert_count = serializers.IntegerField()
```

### 4. View — thin HTTP glue (`dashboard/views.py`)

```python
from .services import get_site_health


@cache_response()
class SiteHealthView(APIView):
    """GET /dashboard/site/{id}/health -- derived status for a site's
    latest summary window. All the logic lives in services.get_site_health."""

    def get(self, request, site_id):
        health = get_site_health(site_id)
        if health is None:
            return Response({"detail": "no summary data for this site"}, status=404)
        logger.info("dashboard.site_health served", extra={"site_id": site_id, "status": health["status"]})
        return Response(SiteHealthSerializer(health).data)
```

### 5. URL (`dashboard/urls.py`)

```python
path("site/<str:site_id>/health", views.SiteHealthView.as_view(), name="dashboard-site-health"),
```

### 6. Tests — one per layer, per `TESTING_GUIDELINES.md`

- **Util** (`core/tests/test_utils.py`): call `classify_temperature(28, 30)` directly, assert `"warning"` — no mocking needed.
- **Service** (`dashboard/tests/test_services.py`): patch `dashboard.services.get_snowflake_client` with a small fake object (not the full `MockSnowflakeClient` — the service only needs `get_site_summary`), assert the returned dict's `status` for a given fixture, and that `None` comes back for an empty result.
- **View** (`dashboard/tests/test_views.py::SiteHealthViewTests`): patch `dashboard.views.get_site_health`, hit `/dashboard/site/A/health` via the Django test client, assert the 200/404 split and that the JSON matches what the mocked service returned.

Each layer's test only mocks the layer directly below it — the view test doesn't need to know Snowflake exists at all, and the service test doesn't spin up an HTTP request.

---

## Quick checklist when adding a module

1. Does this need a **repository**? Only if it queries a database or external API. One repository per data source, one method per query — don't let a repository grow into a dumping ground for unrelated queries.
2. Does this need a **service**? Only if a view would otherwise contain business logic or call more than one repository. If it's a single repository call passed straight to a serializer, skip the service — call the repository from the view, like `SummaryView` does today.
3. Is any part of the logic pure (no I/O)? Pull it into **utils** — it's the cheapest thing in the stack to test and reuse.
4. Does the response go through a **serializer**? Always, per `CODING_GUIDELINES.md` #5 — never return a raw dict/queryset from a view.
5. Did you add a test at the layer where the logic actually lives, not just an end-to-end view test? An end-to-end test alone means a util/service bug only surfaces through an HTTP assertion, which makes failures harder to localize.
