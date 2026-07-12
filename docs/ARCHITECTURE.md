# Architecture

[← Back to README](../README.md)

An enterprise-scale analytics dashboard built with **Django**, **PostgreSQL**, **Kafka**, and **Snowflake**. The system is designed to visualize large-scale IoT data while keeping the operational system isolated from analytical workloads.

---

## System Diagram

```text
                        IoT Devices
                             │
                             ▼
                   Operational System
                             │
                             ▼
                  PostgreSQL (OLTP Database)
                             │
                Change Data Capture (CDC)
                       (e.g. Debezium)
                             │
                             ▼
                           Kafka
                             │
                             ▼
                       Snowflake (OLAP)
                             │
               Pre-aggregated Summary Tables
                             │
                             ▼
                    Django REST Framework
                             │
                             ▼
                 React / Next.js Dashboard
```

---

## Overview

The operational application is responsible for processing IoT data and business transactions.

Dashboard users should **never query the operational database directly** because analytical queries can negatively impact application performance.

Instead, data is continuously replicated from PostgreSQL into Snowflake through Kafka, where it is transformed into analytical models.

The dashboard consumes only aggregated datasets from Snowflake.

---

## Technology Stack

| Layer | Technology |
|--------|------------|
| Backend API | Django + Django REST Framework |
| Operational Database | PostgreSQL |
| Data Streaming | Kafka |
| Change Data Capture | Debezium |
| Analytics Database | Snowflake |
| Response Cache | Redis |
| Frontend | React / Next.js |
| Authentication | Django Authentication / SSO |

---

## Data Flow

```text
IoT Device
    │
    ▼
Operational Application
    │
    ▼
PostgreSQL
    │
    ▼
CDC (Debezium)
    │
    ▼
Kafka
    │
    ▼
Snowflake
    │
    ▼
Aggregation
    │
    ▼
Summary Tables
    │
    ▼
Django API
    │
    ▼
Dashboard
```

---

## Why This Architecture?

### Separation of Concerns

The operational database is optimized for:

- Insert
- Update
- Delete
- Transaction processing

The analytics database is optimized for:

- Aggregation
- Filtering
- Reporting
- Historical analysis

This prevents expensive dashboard queries from affecting the production system.

### Scalability

The architecture supports:

- Billions of telemetry records
- Thousands of concurrent dashboard users
- Multiple downstream consumers
- Independent scaling of services

### Data Pipeline

#### Operational Database

Stores transactional IoT data.

Example:

- Device registration
- Sensor telemetry
- Alerts
- Device configuration

#### CDC

Every insert/update/delete is captured from PostgreSQL.

Instead of polling the database, CDC streams changes into Kafka.

Benefits:

- Low latency
- Minimal database overhead
- Reliable replication

#### Kafka

Kafka acts as the event backbone.

Current consumer:

- Snowflake

Future consumers may include:

- Machine Learning
- Notification Service
- Alert Engine
- Data Lake
- Monitoring

#### Snowflake

Snowflake stores analytical datasets.

Instead of querying raw telemetry tables, scheduled transformations create aggregated tables.

Example:

```text
telemetry_raw
        │
        ▼
5-minute aggregation
        │
        ▼
device_summary_5m
```

Example summary table:

| Timestamp | Site | Avg Temp | Max Temp | Alerts |
|-----------|------|----------|----------|--------|
|10:00|A|26.5|30.2|4|
|10:05|A|26.8|31.0|3|

This significantly reduces query time.

Aggregates are computed and served unrounded; display rounding is the frontend's job — see [`DATA_PRECISION_GUIDELINES.md`](DATA_PRECISION_GUIDELINES.md) for how precision is handled at each stage of the pipeline.

---

## Django Responsibilities

Django is **not responsible for analytics processing**.

Its responsibilities include:

- Authentication
- Authorization
- REST API
- Dashboard endpoints
- Input validation
- Business permissions

Example endpoints:

```text
GET /dashboard/summary
GET /dashboard/devices
GET /dashboard/site/{id}
GET /dashboard/alerts
```

Django queries Snowflake and returns JSON to the frontend.

---

## Database Strategy

### PostgreSQL

Purpose:

- Operational data
- Transaction processing

Characteristics:

- High write throughput
- ACID compliant
- Optimized for OLTP

### Snowflake

Purpose:

- Analytics
- Reporting
- Dashboard

Characteristics:

- Massive parallel processing
- Columnar storage
- Optimized for OLAP

---

## Dashboard Refresh Strategy

Dashboard refresh interval:

```text
Every 5–10 minutes
```

Since near real-time updates are not required, batch ingestion and scheduled transformations provide an efficient balance between freshness, complexity, and cost.

To avoid re-querying Snowflake on every request within that window, dashboard endpoints cache their response in Redis for a short TTL (default 60s, `DASHBOARD_CACHE_TTL_SECONDS`) — well under the 5-minute rollup interval, so cached responses never outlive the data they represent. See `django_app/dashboard/views.py` and `README.md`'s "Caching" section.

---

## Performance Considerations

Avoid querying raw telemetry whenever possible.

Instead:

```text
Raw Telemetry
        │
        ▼
Scheduled Aggregation
        │
        ▼
Summary Tables
        │
        ▼
Dashboard API
```

Benefits:

- Faster response time
- Lower Snowflake compute cost
- Predictable query performance
- Better scalability

---

## Component Scalability

The architecture allows each component to scale independently.

- Django API
- Kafka
- Snowflake
- Frontend

No component is tightly coupled to another.

---

## Advantages

- Clean separation between OLTP and OLAP
- Operational database remains performant
- Highly scalable architecture
- Supports enterprise-scale IoT workloads
- Kafka enables additional downstream consumers
- Snowflake handles analytical workloads efficiently
- Django remains lightweight and focused on API responsibilities
- Easy integration with BI platforms

---

## Suitable Use Cases

- Smart Factory
- Smart City
- Fleet Management
- Energy Monitoring
- Manufacturing
- Industrial IoT
- Environmental Monitoring
- Building Management Systems

---

## Future Improvements

- Materialized or dynamic summary tables
- Data retention policies
- Snowflake Tasks and Streams
- Role-based access control
- WebSocket support for live notifications
- Data quality monitoring
- Distributed tracing and observability
- CI/CD pipeline for automated deployment
