from datetime import UTC, datetime

from django.test import TestCase

from telemetry.models import Alert, Device, Telemetry

# Device/Telemetry/Alert are `managed = False` (see docs/CODING_GUIDELINES.md #2):
# no table exists for them in the test database, so these tests only
# instantiate model objects in memory -- they never call .save() or
# .objects.create().

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class DeviceModelTests(TestCase):
    def test_str_returns_device_code(self):
        device = Device(
            device_code="dev-001", site="A", device_type="sensor", registered_at=NOW, updated_at=NOW
        )
        self.assertEqual(str(device), "dev-001")

    def test_config_defaults_to_empty_dict(self):
        device = Device(
            device_code="dev-002", site="A", device_type="sensor", registered_at=NOW, updated_at=NOW
        )
        self.assertEqual(device.config, {})


class TelemetryModelTests(TestCase):
    def test_str_includes_device_id_and_timestamp(self):
        telemetry = Telemetry(device_id=1, recorded_at=NOW, temperature="26.50", humidity="40.00")
        self.assertEqual(str(telemetry), f"1@{NOW}")

    def test_metadata_defaults_to_empty_dict(self):
        telemetry = Telemetry(device_id=1, recorded_at=NOW)
        self.assertEqual(telemetry.metadata, {})


class AlertModelTests(TestCase):
    def test_str_includes_severity_and_message(self):
        alert = Alert(
            device_id=1, triggered_at=NOW, severity="critical", message="Over temperature threshold"
        )
        self.assertEqual(str(alert), "critical: Over temperature threshold")

    def test_resolved_at_defaults_to_none(self):
        alert = Alert(device_id=1, triggered_at=NOW, severity="warning", message="High humidity")
        self.assertIsNone(alert.resolved_at)
