from unittest.mock import patch

from dashboard.services import get_site_health

# Only the repository is mocked here -- a service test should never need
# Snowflake credentials or a running mock server (see docs/LAYER_GUIDELINES.md,
# "Each layer's test only mocks the layer directly below it").
SERVICE_CLIENT_PATCH = "dashboard.services.get_snowflake_client"


def _fake_client(rows):
    class _FakeClient:
        def get_site_summary(self, site_id):
            return rows

    return _FakeClient()


def test_returns_none_when_site_has_no_summary_data():
    with patch(SERVICE_CLIENT_PATCH, return_value=_fake_client([])):
        assert get_site_health("does-not-exist") is None


def test_status_ok_for_normal_readings():
    rows = [{"avg_temp": 20.0, "max_temp": 25.0, "alert_count": 0}]
    with patch(SERVICE_CLIENT_PATCH, return_value=_fake_client(rows)):
        health = get_site_health("A")
    assert health == {"site": "A", "status": "ok", "avg_temp": 20.0, "max_temp": 25.0, "alert_count": 0}


def test_status_critical_when_max_temp_is_high():
    rows = [{"avg_temp": 29.0, "max_temp": 33.0, "alert_count": 5}]
    with patch(SERVICE_CLIENT_PATCH, return_value=_fake_client(rows)):
        health = get_site_health("B")
    assert health["status"] == "critical"


def test_uses_the_latest_row_when_multiple_are_returned():
    rows = [
        {"avg_temp": 33.0, "max_temp": 33.0, "alert_count": 5},
        {"avg_temp": 20.0, "max_temp": 21.0, "alert_count": 0},
    ]
    with patch(SERVICE_CLIENT_PATCH, return_value=_fake_client(rows)):
        health = get_site_health("A")
    assert health["status"] == "critical"
