from unittest.mock import patch

from django.test import TestCase

from core.snowflake_client import MockSnowflakeClient

# Every test in this module runs against the mock Snowflake client -- no
# credentials or docker-compose stack required (see docs/TESTING_GUIDELINES.md #1).
MOCK_CLIENT_PATCH = patch("dashboard.views.get_snowflake_client", return_value=MockSnowflakeClient())


class DashboardEndpointsTests(TestCase):
    def setUp(self):
        self.mock_get_client = MOCK_CLIENT_PATCH.start()
        self.addCleanup(MOCK_CLIENT_PATCH.stop)

    def test_all_endpoints_return_200(self):
        for url in ["/dashboard/summary", "/dashboard/devices", "/dashboard/site/A", "/dashboard/alerts"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_summary_row_matches_serializer_contract(self):
        response = self.client.get("/dashboard/summary")
        row = response.json()[0]
        self.assertEqual(set(row.keys()), {"window_start", "site", "avg_temp", "max_temp", "alert_count"})

    def test_devices_returns_distinct_sites(self):
        response = self.client.get("/dashboard/devices")
        self.assertEqual(response.json(), [{"site": "A"}, {"site": "B"}])

    def test_site_summary_filters_by_site_id(self):
        response = self.client.get("/dashboard/site/A")
        self.assertTrue(response.json())
        self.assertTrue(all(row["site"] == "A" for row in response.json()))

    def test_site_summary_empty_for_unknown_site(self):
        response = self.client.get("/dashboard/site/does-not-exist")
        self.assertEqual(response.json(), [])

    def test_alerts_only_include_positive_alert_counts(self):
        response = self.client.get("/dashboard/alerts")
        self.assertTrue(response.json())
        self.assertTrue(all(row["alert_count"] > 0 for row in response.json()))
