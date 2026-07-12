from django.db import models

# These models mirror the operational schema owned by PostgreSQL
# (see sql/init_operational_schema.sql). They are `managed = False`:
# Django never migrates or writes to this schema -- the operational
# application is the system of record, and CDC/Kafka/Snowflake handle
# everything downstream of it.


class Device(models.Model):
    device_code = models.CharField(max_length=64, unique=True)
    site = models.CharField(max_length=64)
    device_type = models.CharField(max_length=64)
    config = models.JSONField(default=dict)
    registered_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "devices"

    def __str__(self):
        return self.device_code


class Telemetry(models.Model):
    device = models.ForeignKey(Device, on_delete=models.DO_NOTHING, db_column="device_id")
    recorded_at = models.DateTimeField()
    temperature = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    humidity = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        managed = False
        db_table = "telemetry"

    def __str__(self):
        return f"{self.device_id}@{self.recorded_at}"


class Alert(models.Model):
    device = models.ForeignKey(Device, on_delete=models.DO_NOTHING, db_column="device_id")
    triggered_at = models.DateTimeField()
    severity = models.CharField(max_length=32)
    message = models.TextField()
    resolved_at = models.DateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "alerts"

    def __str__(self):
        return f"{self.severity}: {self.message}"
