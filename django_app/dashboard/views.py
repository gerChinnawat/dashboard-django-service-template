import logging

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.response import Response
from rest_framework.views import APIView

from core.snowflake_client import get_snowflake_client

from .serializers import AlertRowSerializer, DeviceSerializer, SummaryRowSerializer

logger = logging.getLogger(__name__)


def cache_response():
    """Caches a view's full response keyed by request path (Redis-backed,
    see CACHES in settings) -- device_summary_5m only changes every 5
    minutes, so short-lived caching cuts repeated Snowflake queries."""
    return method_decorator(cache_page(settings.DASHBOARD_CACHE_TTL_SECONDS), name="get")


@cache_response()
class SummaryView(APIView):
    """GET /dashboard/summary -- pre-aggregated device_summary_5m rollup."""

    def get(self, request):
        rows = get_snowflake_client().get_summary()
        logger.info("dashboard.summary served", extra={"row_count": len(rows)})
        return Response(SummaryRowSerializer(rows, many=True).data)


@cache_response()
class DevicesView(APIView):
    """GET /dashboard/devices -- distinct sites/devices present in the summary data."""

    def get(self, request):
        rows = get_snowflake_client().get_devices()
        logger.info("dashboard.devices served", extra={"row_count": len(rows)})
        return Response(DeviceSerializer(rows, many=True).data)


@cache_response()
class SiteSummaryView(APIView):
    """GET /dashboard/site/{id} -- summary rows filtered to a single site."""

    def get(self, request, site_id):
        rows = get_snowflake_client().get_site_summary(site_id)
        logger.info("dashboard.site_summary served", extra={"site_id": site_id, "row_count": len(rows)})
        return Response(SummaryRowSerializer(rows, many=True).data)


@cache_response()
class AlertsView(APIView):
    """GET /dashboard/alerts -- summary windows with at least one alert."""

    def get(self, request):
        rows = get_snowflake_client().get_alerts()
        logger.info("dashboard.alerts served", extra={"row_count": len(rows)})
        return Response(AlertRowSerializer(rows, many=True).data)
