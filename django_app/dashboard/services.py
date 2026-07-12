"""Business logic that doesn't belong in a view or a repository -- see
docs/LAYER_GUIDELINES.md, "Service". Never imports rest_framework: a
service takes plain arguments and returns plain data, so it's callable
from a view, a management command, or a test with no HTTP involved."""

from core.snowflake_client import get_snowflake_client
from core.utils import classify_temperature


def get_site_health(site_id):
    """Combines the site's latest Snowflake summary row with the
    classify_temperature util to produce a derived status. Returns None
    if the site has no summary data (the view turns that into a 404)."""
    rows = get_snowflake_client().get_site_summary(site_id)
    if not rows:
        return None

    latest = rows[0]
    return {
        "site": site_id,
        "status": classify_temperature(latest["avg_temp"], latest["max_temp"]),
        "avg_temp": latest["avg_temp"],
        "max_temp": latest["max_temp"],
        "alert_count": latest["alert_count"],
    }
