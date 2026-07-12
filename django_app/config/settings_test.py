"""Settings for the unit test suite: SQLite in place of the operational
Postgres database, so `pytest` never needs docker-compose running.
Integration/e2e tests (top-level `tests/`) exercise the real stack instead.
"""

from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
