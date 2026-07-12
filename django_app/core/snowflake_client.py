"""Config-driven client for querying Snowflake summary tables.

Django never runs analytics processing itself -- it only reads the
pre-aggregated tables that the Snowflake task in sql/snowflake_aggregation.sql
maintains. When Snowflake credentials aren't configured (e.g. local dev with
no Snowflake account), `get_snowflake_client()` returns a mock client that
returns fixture data shaped like the tables it stands in for.
"""

import logging
import time
from datetime import UTC, datetime, timedelta

from django.conf import settings

logger = logging.getLogger(__name__)


class BaseSnowflakeClient:
    def get_summary(self):
        raise NotImplementedError

    def get_devices(self):
        raise NotImplementedError

    def get_site_summary(self, site_id):
        raise NotImplementedError

    def get_alerts(self):
        raise NotImplementedError


class SnowflakeClient(BaseSnowflakeClient):
    """Queries the real Snowflake summary tables."""

    def __init__(self, config):
        self._config = config

    def _connect(self):
        import snowflake.connector

        return snowflake.connector.connect(
            account=self._config["ACCOUNT"],
            user=self._config["USER"],
            password=self._config["PASSWORD"],
            warehouse=self._config["WAREHOUSE"],
            database=self._config["DATABASE"],
            schema=self._config["SCHEMA"],
        )

    def _query(self, sql, params=None):
        started_at = time.monotonic()
        conn = self._connect()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, params or {})
            rows = cursor.fetchall()
            logger.info(
                "snowflake query executed",
                extra={
                    "row_count": len(rows),
                    "duration_ms": round((time.monotonic() - started_at) * 1000, 1),
                },
            )
            return rows
        except Exception:
            logger.exception("snowflake query failed", extra={"sql": sql})
            raise
        finally:
            conn.close()

    def get_summary(self):
        return self._query(
            "SELECT window_start, site, avg_temp, max_temp, alert_count "
            "FROM device_summary_5m ORDER BY window_start DESC LIMIT 100"
        )

    def get_devices(self):
        return self._query("SELECT DISTINCT site AS site FROM device_summary_5m ORDER BY site")

    def get_site_summary(self, site_id):
        return self._query(
            "SELECT window_start, site, avg_temp, max_temp, alert_count "
            "FROM device_summary_5m WHERE site = %(site_id)s ORDER BY window_start DESC LIMIT 100",
            {"site_id": site_id},
        )

    def get_alerts(self):
        return self._query(
            "SELECT window_start, site, alert_count FROM device_summary_5m "
            "WHERE alert_count > 0 ORDER BY window_start DESC LIMIT 100"
        )


class MockSnowflakeClient(BaseSnowflakeClient):
    """Returns fixture data shaped like the README's example summary table."""

    def _fixture_rows(self):
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        return [
            {
                "window_start": now - timedelta(minutes=5 * i),
                "site": site,
                "avg_temp": 26.5 + i * 0.3,
                "max_temp": 30.2 + i * 0.3,
                "alert_count": max(4 - i, 0),
            }
            for i, site in enumerate(["A", "A", "B", "B"])
        ]

    def get_summary(self):
        return self._fixture_rows()

    def get_devices(self):
        sites = sorted({row["site"] for row in self._fixture_rows()})
        return [{"site": site} for site in sites]

    def get_site_summary(self, site_id):
        return [row for row in self._fixture_rows() if row["site"] == site_id]

    def get_alerts(self):
        return [row for row in self._fixture_rows() if row["alert_count"] > 0]


def get_snowflake_client():
    config = settings.SNOWFLAKE
    if config.get("ACCOUNT"):
        logger.debug("using real SnowflakeClient", extra={"account": config["ACCOUNT"]})
        return SnowflakeClient(config)
    logger.debug("SNOWFLAKE_ACCOUNT unset, using MockSnowflakeClient")
    return MockSnowflakeClient()
