from django.urls import include, path

urlpatterns = [
    path("", include("django_prometheus.urls")),  # exposes /metrics
    path("dashboard/", include("dashboard.urls")),
]
