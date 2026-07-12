# Security Policy

[← Back to README](../README.md)

This repository is a **local development template** for the CDC → Kafka → Snowflake → Django architecture described in [`ARCHITECTURE.md`](ARCHITECTURE.md). Several things in it are intentionally simplified for `docker compose up` convenience and are **not safe as shipped for any shared, staging, or production environment**. This document lists those gaps explicitly so they aren't mistaken for reviewed defaults.

---

## Reporting a Vulnerability

If you find a security issue in code you've built on top of this template (or in the template itself), please report it privately rather than opening a public issue:

- If this repo is hosted on GitHub, use **Security → Report a vulnerability** (private security advisory) on the repo.
- Otherwise, contact the maintainer directly rather than filing a public issue, so any real deployment isn't exposed while a fix is prepared.

Please include: the affected file/component, reproduction steps, and the potential impact. You should expect an acknowledgment before a public disclosure timeline is discussed.

---

## Known Gaps in This Template (read before deploying anywhere but localhost)

### 1. The dashboard API has no authentication

`django_app/config/settings.py` sets:

```python
"DEFAULT_AUTHENTICATION_CLASSES": [],
"DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
```

Every endpoint in `dashboard/views.py` (`/dashboard/summary`, `/devices`, `/site/{id}`, `/alerts`) is open to any caller. This matches the README's "Future Improvements: Role-based access control" — it has not been built yet.

**Before exposing this API beyond localhost:** add real authentication (session, token, or SSO per the README's "Django Authentication / SSO" line) and permission classes, and re-enable `django.contrib.auth` / `django.contrib.contenttypes` in `INSTALLED_APPS`.

### 2. The Debezium connector config contains a plaintext password

`connectors/postgres-debezium-connector.json` has `"database.password": "iot_app_password"` committed in plain text. It matches the local-only default in `.env.example` (`POSTGRES_PASSWORD`), so it isn't a live secret today — but it's a pattern that must not be repeated with real credentials.

**Before pointing this at any non-throwaway database:** externalize the password using [Kafka Connect Config Providers](https://kafka.apache.org/documentation/#connect_configproviders) (e.g. `FileConfigProvider`, or a vault/secrets-manager provider) instead of inlining it in the connector JSON, and stop committing the resulting file if it contains real values.

### 3. Default credentials in `.env.example` and `docker-compose.yml`

`iot_app` / `iot_app_password` (Postgres) are placeholder local-dev credentials. `docker-compose.yml` and `sql/init_operational_schema.sql` assume them.

**Rotate every one of these** before using this compose file anywhere other than a disposable local environment — including in shared CI runners, if the containers are reachable from outside the runner.

### 4. Kafka broker and Kafka Connect REST API are unauthenticated

`docker-compose.yml` exposes Kafka on `9092` and the Kafka Connect REST API on `8083` with no `SASL`/TLS configuration — anyone who can reach those ports can read all CDC topics or reconfigure/delete the connector via the REST API.

**Do not** publish these ports beyond `localhost`/an isolated network. For anything beyond local dev, add `SASL_SSL` listeners and Connect REST API authentication.

### 5. Snowflake credentials

`core/snowflake_client.py` reads Snowflake credentials from environment variables (`SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`, etc.) via `django_app/config/settings.py`, and `.env` is gitignored (see `.gitignore`). This is the correct pattern — **never** hardcode real Snowflake credentials into `settings.py`, `snowflake_client.py`, or commit them in a connector/config file. Prefer key-pair authentication or an external secrets manager over a long-lived password where your Snowflake account supports it.

### 6. The `/metrics` endpoint is unauthenticated

`django-prometheus` (wired in `config/settings.py`/`config/urls.py`) exposes request-latency and DB-query metrics at `/metrics` with no auth — this is standard for Prometheus (scrapers don't usually authenticate), but it does mean anyone who can reach the Django process can see request-volume/timing data for every endpoint, including `/dashboard/site/{id}` calls with real site identifiers.

**Before exposing this beyond localhost:** restrict `/metrics` at the network/ingress level (e.g. only allow your Prometheus scraper's IP/service mesh identity), rather than making it internet-reachable alongside the dashboard API.

### 7. Redis (dashboard cache) is unauthenticated and unencrypted

`docker-compose.yml` exposes Redis on `6379` with no `requirepass`/ACL and no TLS — the same gap as #4 above, applied to the cache layer. Redis only ever holds cached dashboard *responses* (see `README.md`'s "Caching" section), not credentials or operational data, but anyone who can reach port `6379` can read every cached response or flush the cache to force load back onto Snowflake.

**Do not** publish `6379` beyond `localhost`/an isolated network. For anything beyond local dev, set `requirepass` (or ACLs) and connect over TLS, updating `REDIS_URL` accordingly.

---

## Minimum Hardening Checklist Before Any Non-Local Deployment

- [ ] Add authentication + permission classes to the Django API (`dashboard/views.py`, `config/settings.py`)
- [ ] Move the Debezium connector password to a Config Provider / secrets manager
- [ ] Rotate all default Postgres/Kafka credentials
- [ ] Put TLS + SASL in front of Kafka and the Kafka Connect REST API; do not expose `9092`/`8083` publicly
- [ ] Confirm `.env` is never committed (`.gitignore` already covers this — verify before every commit with untracked secrets)
- [ ] Restrict the Snowflake role used by `SnowflakeClient` to read-only access on the summary tables it queries (`device_summary_5m`, etc.) — it should never need write access to `telemetry_raw`
- [ ] Restrict `/metrics` to trusted scrapers only (network policy/ingress rule), not publicly reachable
- [ ] Set a Redis `requirepass`/ACL and enable TLS; do not expose `6379` publicly
