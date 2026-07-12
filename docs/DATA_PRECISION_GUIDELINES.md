# Data Precision Guidelines

How numeric sensor values are stored, aggregated, and displayed across this pipeline
(`Postgres → Debezium → Kafka → Snowflake → Django REST API → dashboard`), and what to do
when adding a new measurement.

## The rule

- **Store raw sensor values at full source precision** (Postgres, `sql/init_operational_schema.sql`).
- **Aggregate and calculate on raw values** (Snowflake, `sql/snowflake_aggregation.sql`).
- **Round only at display time** (the dashboard frontend — not yet built; the API returns unrounded values).

This keeps analytics, auditing, and long-term aggregation accurate while dashboards stay readable.
Nothing between the sensor and the screen should round.

## Where precision is defined today, layer by layer

| Layer | File | Type | Notes |
|-------|------|------|-------|
| Postgres (OLTP, system of record) | `sql/init_operational_schema.sql` | `temperature NUMERIC(6,2)`, `humidity NUMERIC(6,2)` | Source precision — sensors in this stack report 2 decimal places, so `NUMERIC(6,2)` stores them exactly. This is a storage bound, not display rounding. |
| Django mirror models | `django_app/telemetry/models.py` | `DecimalField(max_digits=6, decimal_places=2)` | Must mirror the Postgres column exactly (`managed = False` — Django never migrates this schema). |
| Snowflake raw + summary | `sql/snowflake_aggregation.sql` | `FLOAT` (`telemetry_raw.temperature/humidity`, `device_summary_5m.avg_temp/max_temp`) | Aggregates (`AVG`, `MAX`) run on unrounded values. Counts (`alert_count`) are `NUMBER`. |
| API serializers | `django_app/dashboard/serializers.py` | `FloatField` (`avg_temp`, `max_temp`), `IntegerField` (`alert_count`) | The serializer passes values through unrounded — do **not** add rounding here; the API contract is raw aggregate values. |
| Mock client fixtures | `django_app/core/snowflake_client.py` | Python floats (e.g. `26.5`, `30.2`) | Keep fixture precision shaped like the real summary table. |
| Dashboard display | (no frontend yet) | — | Rounding happens here and only here, per the table below. |

## Recommended display precision

For the measurements this project has (or is likely to add — IoT device telemetry):

| Measurement | Unit | Display precision | Example |
|-------------|------|-------------------|---------|
| Temperature (`avg_temp`, `max_temp`) | °C | 1 decimal place | 26.8 °C |
| Humidity | %RH | 0–1 decimal place | 68% RH |
| Alert count | — | integer (no rounding) | 4 |

Keep display precision consistent across all dashboard views for the same measurement.

## Worked example (this pipeline)

```text
Sensor reading            temperature = 26.83 °C
Postgres telemetry row    26.83            (NUMERIC(6,2), exact)
Debezium → Kafka          26.83            (CDC copies the value verbatim)
Snowflake telemetry_raw   26.83            (FLOAT)
device_summary_5m         avg_temp = 26.766666...  (AVG over the 5-min window, unrounded)
API response              {"avg_temp": 26.766666666666666}
Dashboard display         26.8 °C          (rounded at render time only)
```

## Adding a new measurement — checklist

1. **Postgres column** (`sql/init_operational_schema.sql`): use `NUMERIC(p,s)` sized to the
   sensor's actual reported precision for continuous measurements, matching the existing
   `temperature`/`humidity` pattern. Use `NUMERIC` (never `DOUBLE PRECISION`/`FLOAT`) for anything
   that feeds billing, compliance, or long-horizon accumulation (e.g. energy in kWh) — exact
   decimal arithmetic prevents float error from accumulating.
2. **Mirror it in `django_app/telemetry/models.py`** with a matching `DecimalField` — same
   `max_digits`/`decimal_places`, keep `managed = False`.
3. **Snowflake** (`sql/snowflake_aggregation.sql`): add the column to `telemetry_raw` (`FLOAT` is
   fine for continuous measurements; `NUMBER(p,s)` for billing-grade values) and, if it should
   appear on the dashboard, add the aggregate to the `device_summary_5m` MERGE.
4. **Serializer** (`django_app/dashboard/serializers.py`): expose the aggregate as a `FloatField`
   (or `DecimalField` for billing-grade values) — unrounded. Serializers are the API contract;
   tests assert the serialized shape (see `docs/TESTING_GUIDELINES.md` #4).
5. **Mock client** (`django_app/core/snowflake_client.py`): extend `_fixture_rows()` so the mock
   stays shaped like the real summary table.
6. **Round only in the frontend**, using the display-precision table above.

## Best practices

- ✅ Store raw sensor data without rounding; round only at render time.
- ✅ Run all aggregation (`AVG`, `MAX`, sums) on unrounded values.
- ✅ Keep the Postgres column, Django mirror model, Snowflake column, and serializer field types in sync when adding a measurement.
- ✅ Use exact decimal types (`NUMERIC`) for anything with billing/financial/compliance implications.
- ❌ Don't add `round()` in views, serializers, or the Snowflake client — display formatting is the frontend's job.
- ❌ Don't widen or narrow `NUMERIC(6,2)` in the Django model alone — Postgres owns the schema; change the SQL first and mirror it.
