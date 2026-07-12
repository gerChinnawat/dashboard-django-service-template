import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "change-me-in-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django_prometheus",
    "django.contrib.staticfiles",
    "rest_framework",
    "telemetry",
    "dashboard",
]

# PrometheusBeforeMiddleware/AfterMiddleware must stay first/last respectively
# so request-latency metrics wrap every other middleware.
MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# The operational database (PostgreSQL). Django reads `telemetry` models from it
# for local reference only -- it does not run analytics queries against it.
# Wrapped with django-prometheus so query count/latency show up in /metrics.
DATABASES = {
    "default": {
        "ENGINE": "django_prometheus.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "iot_operational"),
        "USER": os.environ.get("POSTGRES_USER", "iot_app"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "iot_app_password"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Caches dashboard responses to cut down on repeated Snowflake queries --
# the underlying device_summary_5m rollup only changes every 5 minutes
# (see sql/snowflake_aggregation.sql), so a short TTL is safe.
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL", "redis://localhost:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}
DASHBOARD_CACHE_TTL_SECONDS = int(os.environ.get("DASHBOARD_CACHE_TTL_SECONDS", "60"))

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    # No auth app installed yet (see README's "Future Improvements": RBAC/SSO).
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
}

# Snowflake (analytics OLAP database). Left blank in local dev -- the
# dashboard app falls back to a mock client when these are unset.
SNOWFLAKE = {
    "ACCOUNT": os.environ.get("SNOWFLAKE_ACCOUNT", ""),
    "USER": os.environ.get("SNOWFLAKE_USER", ""),
    "PASSWORD": os.environ.get("SNOWFLAKE_PASSWORD", ""),
    "WAREHOUSE": os.environ.get("SNOWFLAKE_WAREHOUSE", ""),
    "DATABASE": os.environ.get("SNOWFLAKE_DATABASE", ""),
    "SCHEMA": os.environ.get("SNOWFLAKE_SCHEMA", ""),
}

# Structured (JSON) logging so log lines are parseable by a log aggregator
# (ELK/Loki/CloudWatch) without a separate parsing step. `dashboard` and
# `core` loggers cover the API and Snowflake-client layers respectively;
# everything else falls through to the root logger.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "dashboard": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "core": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}
