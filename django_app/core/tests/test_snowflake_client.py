from django.test import override_settings

from core.snowflake_client import MockSnowflakeClient, SnowflakeClient, get_snowflake_client

EMPTY_SNOWFLAKE_CONFIG = {
    "ACCOUNT": "",
    "USER": "",
    "PASSWORD": "",
    "WAREHOUSE": "",
    "DATABASE": "",
    "SCHEMA": "",
}

CONFIGURED_SNOWFLAKE_CONFIG = {**EMPTY_SNOWFLAKE_CONFIG, "ACCOUNT": "acme-corp"}


@override_settings(SNOWFLAKE=EMPTY_SNOWFLAKE_CONFIG)
def test_falls_back_to_mock_client_when_account_unset():
    assert isinstance(get_snowflake_client(), MockSnowflakeClient)


@override_settings(SNOWFLAKE=CONFIGURED_SNOWFLAKE_CONFIG)
def test_uses_real_client_when_account_configured():
    assert isinstance(get_snowflake_client(), SnowflakeClient)


def test_mock_summary_rows_match_serializer_shape():
    rows = MockSnowflakeClient().get_summary()
    assert rows
    for row in rows:
        assert set(row.keys()) == {"window_start", "site", "avg_temp", "max_temp", "alert_count"}


def test_mock_devices_are_distinct_sites():
    devices = MockSnowflakeClient().get_devices()
    sites = [d["site"] for d in devices]
    assert sites == sorted(set(sites))


def test_mock_site_summary_filters_by_site():
    rows = MockSnowflakeClient().get_site_summary("A")
    assert rows
    assert all(row["site"] == "A" for row in rows)


def test_mock_site_summary_returns_empty_for_unknown_site():
    assert MockSnowflakeClient().get_alerts()
    assert MockSnowflakeClient().get_site_summary("does-not-exist") == []


def test_mock_alerts_only_include_rows_with_alerts():
    rows = MockSnowflakeClient().get_alerts()
    assert rows
    assert all(row["alert_count"] > 0 for row in rows)
