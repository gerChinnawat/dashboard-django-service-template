from rest_framework import serializers


class SummaryRowSerializer(serializers.Serializer):
    window_start = serializers.DateTimeField()
    site = serializers.CharField()
    avg_temp = serializers.FloatField()
    max_temp = serializers.FloatField()
    alert_count = serializers.IntegerField()


class DeviceSerializer(serializers.Serializer):
    site = serializers.CharField()


class AlertRowSerializer(serializers.Serializer):
    window_start = serializers.DateTimeField()
    site = serializers.CharField()
    alert_count = serializers.IntegerField()
