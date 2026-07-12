from django.urls import path

from . import views

urlpatterns = [
    path("summary", views.SummaryView.as_view(), name="dashboard-summary"),
    path("devices", views.DevicesView.as_view(), name="dashboard-devices"),
    path("site/<str:site_id>", views.SiteSummaryView.as_view(), name="dashboard-site"),
    path("site/<str:site_id>/health", views.SiteHealthView.as_view(), name="dashboard-site-health"),
    path("alerts", views.AlertsView.as_view(), name="dashboard-alerts"),
]
