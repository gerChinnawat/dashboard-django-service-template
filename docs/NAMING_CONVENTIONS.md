# Naming Conventions

[← Back to README](../README.md)

Naming rules for this repo, enforced by `make lint` (ruff's `N` — pep8-naming — rule set, added in `pyproject.toml`). See also [`CODING_GUIDELINES.md`](CODING_GUIDELINES.md) and [`LAYER_GUIDELINES.md`](LAYER_GUIDELINES.md) for where code should live; this doc only covers what to call it.

---

## Enforcement: linted, not auto-fixed

`make format` (black + `ruff check --fix`) auto-fixes import order, quote style, upgrades, etc. — but **not naming**. Renaming a class or function isn't safe to do blindly: a formatter can't know every call site, docstring, or external reference, so an automatic rename risks silently breaking something. Naming violations are instead a `make lint` / CI failure — caught before merge, fixed by a human with full context on the rename's blast radius.

```bash
make lint      # ruff check . (includes N rules) + black --check .  -- CI runs this
make format    # applies what CAN be auto-fixed (not naming)
```

If `make lint` fails on an `N`-prefixed rule (e.g. `N802 invalid-function-name`), rename the offending identifier and its call sites yourself, then re-run `make lint`.

---

## Python identifiers

Standard PEP 8, matching what's already in this codebase:

| Kind | Convention | Example |
|---|---|---|
| Module / file | `snake_case.py` | `snowflake_client.py`, `settings_test.py` |
| Package / Django app | `snake_case`, short, singular-or-plural as reads naturally | `dashboard`, `telemetry`, `core` |
| Class | `PascalCase` | `SnowflakeClient`, `MockSnowflakeClient`, `SummaryRowSerializer`, `DeviceHealthView` |
| Function / method | `snake_case` | `get_snowflake_client()`, `get_site_summary(site_id)` |
| Variable / parameter | `snake_case` | `device_code`, `avg_temp`, `row_count` |
| Constant | `UPPER_SNAKE_CASE` | `DASHBOARD_CACHE_TTL_SECONDS`, `KAFKA_BOOTSTRAP_SERVERS` |
| "Private" (module-internal) | leading underscore | `_connect()`, `_query()`, `_fixture_rows()` (see `core/snowflake_client.py`) |
| Exception class | `PascalCase`, ends in `Error` (or occasionally the bare condition, e.g. `DeviceNotFound`) | `DeviceNotFoundError` |

`N`-rule violations to watch for specifically: `N801` (class not CamelCase), `N802` (function not snake_case), `N806` (non-constant variable in ALL_CAPS inside a function), `N815`/`N816` (mixedCase class/global variables — the most common accidental violation when porting code from a JS/Java example).

---

## Layer-specific naming

Ties into [`LAYER_GUIDELINES.md`](LAYER_GUIDELINES.md) — the layer a symbol belongs to shapes its name:

- **Views**: `<Noun>View`, one per HTTP verb+resource — `SummaryView`, `DeviceHealthView`. Not `SummaryAPIView` or `SummaryViewSet` unless it actually is one (we use plain `APIView`, not DRF viewsets, in this codebase).
- **Serializers**: `<Noun>Serializer`, named after what it represents on the wire, not its source table — `SummaryRowSerializer` (a row of `device_summary_5m`), not `DeviceSummary5mSerializer`. See "Serializer (DTO)" in `LAYER_GUIDELINES.md` for why the DTO's name should reflect the API contract, not the backing schema.
- **Services**: `get_<noun>()` / `<verb>_<noun>()` free functions in `<app>/services.py`, not classes, unless the service genuinely needs to hold state across calls — `get_device_health(device_code)`, not `DeviceHealthService().get(device_code)`.
- **Repositories**: `get_<noun>_by_<key>()` / `get_<plural_noun>()`, mirroring the Snowflake client's existing method names — `get_device_by_code(device_code)`, `get_summary()`, `get_site_summary(site_id)`.
- **Utils**: verb-first, describing the pure transformation — `classify_temperature(avg_temp, max_temp)`, not `TemperatureClassifier` (a class implies state; a util shouldn't have any).
- **Models**: singular noun matching the table's singular form — `Device`, `Telemetry`, `Alert` (mirroring `devices`, `telemetry`, `alerts` via `Meta.db_table`, per `CODING_GUIDELINES.md` #2).

---

## Tests

Match the existing pattern in `dashboard/tests/test_views.py` / `tests/integration/test_cdc_pipeline.py`: test files are `test_<module>.py`, test methods are `test_<what>_<condition_or_expectation>` — full sentences, not abbreviations, since the name is the only documentation a failing-test summary line gives you:

**Good**: `test_site_summary_filters_by_site_id`, `test_summary_row_matches_serializer_contract`

**Bad**: `test_1`, `test_site_summary`, `test_it_works`

---

## Django/API-surface naming (not covered by ruff)

Ruff's `N` rules only cover Python identifiers — the following are conventions to follow by hand, not lint-enforced:

- **URL paths**: lowercase, hyphen-free, matching the resource — `/dashboard/summary`, `/dashboard/site/<site_id>`, not `/dashboard/getSummary` or `/dashboard/Summary`.
- **Serializer (JSON) fields**: `snake_case`, matching Python convention rather than camelCase — `window_start`, `avg_temp` — since this API has no JS frontend consumer yet forcing a camelCase contract (see `CLAUDE.md`: "there is no frontend yet").
- **Environment variables**: `UPPER_SNAKE_CASE`, prefixed by the system they configure — `SNOWFLAKE_ACCOUNT`, `KAFKA_BOOTSTRAP_SERVERS`, `DASHBOARD_CACHE_TTL_SECONDS`.
- **Docker Compose services / container names**: `iot-<service>` — `iot-postgres`, `iot-kafka`, `iot-redis` (see `docker-compose.yml`).
