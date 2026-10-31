"""
Base settings shared by every environment.

Environment-specific values come from a `.env` file (see `.env.example`) or
real environment variables, read through django-environ.
"""

from datetime import timedelta
from pathlib import Path

import environ

from config.unfold import UNFOLD  # noqa: F401

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:3000"]),
    CSRF_TRUSTED_ORIGINS=(list, ["http://localhost:3000"]),
    FRONTEND_URL=(str, "http://localhost:3000"),
    REDIS_URL=(str, "redis://127.0.0.1:6379/0"),
    CELERY_BROKER_URL=(str, "redis://127.0.0.1:6379/1"),
    CHANNEL_LAYER_URL=(str, "redis://127.0.0.1:6379/2"),
    EMAIL_BACKEND=(str, "django.core.mail.backends.console.EmailBackend"),
    DEFAULT_FROM_EMAIL=(str, "Leepa Sports <no-reply@leepasports.com>"),
    GOOGLE_OAUTH_CLIENT_ID=(str, ""),
    SITE_NAME=(str, "Leepa Sports"),
    ADMIN_NOTIFICATION_EMAILS=(list, []),
    JWT_ACCESS_MINUTES=(int, 15),
    JWT_REFRESH_DAYS=(int, 7),
    DEFAULT_CURRENCY=(str, "USD"),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
SITE_NAME = env("SITE_NAME")
FRONTEND_URL = env("FRONTEND_URL").rstrip("/")
ADMIN_NOTIFICATION_EMAILS = env("ADMIN_NOTIFICATION_EMAILS")
DEFAULT_CURRENCY = env("DEFAULT_CURRENCY")
ADMIN_URL = env("ADMIN_URL", default="admin/")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "daphne",
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]

THIRD_PARTY_APPS = [
    "django_extensions",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "channels",
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.pricing",
    "apps.cart",
    "apps.quotes",
    "apps.orders",
    "apps.payments",
    "apps.notifications",
    "apps.search",
    "apps.chat",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database — PostgreSQL only (we rely on full-text search, trigram, JSONB,
# partial indexes and `select_for_update`).
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        **env.db("DATABASE_URL", default="postgres://postgres:postgres@127.0.0.1:5432/leepasports"),
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
        "CONN_HEALTH_CHECKS": True,
        "ATOMIC_REQUESTS": False,
        "OPTIONS": {"connect_timeout": 10},
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Cache / Redis
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "leepa",
        "TIMEOUT": 300,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,
            "SOCKET_CONNECT_TIMEOUT": 2,
            "SOCKET_TIMEOUT": 2,
        },
    }
}
DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [env("CHANNEL_LAYER_URL")], "capacity": 1500, "expiry": 10},
    }
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "UTC"
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_SOFT_TIME_LIMIT = 60
CELERY_TASK_TIME_LIMIT = 120
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {
    "expire-stale-quotes": {
        "task": "apps.quotes.tasks.expire_stale_quotes",
        "schedule": timedelta(hours=1),
    },
    "release-abandoned-carts": {
        "task": "apps.cart.tasks.purge_abandoned_guest_carts",
        "schedule": timedelta(hours=6),
    },
    "flush-blacklisted-tokens": {
        "task": "apps.accounts.tasks.flush_expired_tokens",
        "schedule": timedelta(days=1),
    },
}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
GOOGLE_OAUTH_CLIENT_ID = env("GOOGLE_OAUTH_CLIENT_ID")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 24,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/min",
        "user": "600/min",
        "auth": "10/min",
        "auth_burst": "30/hour",
        "search": "90/min",
        "chat": "120/min",
    },
    "NON_FIELD_ERRORS_KEY": "detail",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env("JWT_ACCESS_MINUTES")),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env("JWT_REFRESH_DAYS")),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default=SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.auth.TokenObtainSerializer",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Leepa Sports B2B API",
    "DESCRIPTION": "Wholesale sportswear ordering platform.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# ---------------------------------------------------------------------------
# I18N / static / media
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
if EMAIL_BACKEND.endswith("smtp.EmailBackend"):
    EMAIL_HOST = env("EMAIL_HOST", default="")
    EMAIL_PORT = env.int("EMAIL_PORT", default=587)
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
    EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
    EMAIL_TIMEOUT = 15

# ---------------------------------------------------------------------------
# CORS / security
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "x-request-id",
    "x-company-id",
    "x-cart-token",
    "x-session-key",
]
CORS_EXPOSE_HEADERS = ["x-request-id"]
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# ---------------------------------------------------------------------------
# Business configuration
# ---------------------------------------------------------------------------
LEEPA = {
    "CART_GUEST_TTL_DAYS": 14,
    "QUOTE_VALIDITY_DAYS": 14,
    "ORDER_NUMBER_PREFIX": "LS",
    "QUOTE_NUMBER_PREFIX": "LQ",
    "DEFAULT_LEAD_TIME_DAYS": 21,
    "SUPPORT_EMAIL": env("SUPPORT_EMAIL", default="sales@leepasports.com"),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "%(asctime)s %(levelname)s [%(name)s] %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        "apps": {"level": "INFO"},
    },
}

# ---------------------------------------------------------------------------
# django-extensions
# ---------------------------------------------------------------------------
SHELL_PLUS = "ipython"
SHELL_PLUS_PRINT_SQL = False
SHELL_PLUS_PRINT_SQL_TRUNCATE = 1000
SHELL_PLUS_IMPORTS = [
    "from decimal import Decimal",
    "from django.db.models import Count, Sum, F, Q, Prefetch",
    "from apps.pricing.services import compute_price, base_price_for, fabric_cost",
    "from apps.pricing.selectors import resolve_configuration",
    "from apps.orders import services as order_services",
    "from apps.quotes import services as quote_services",
    "from apps.cart import services as cart_services",
    "from apps.catalog.services import category_tree",
    "from apps.notifications.events import emit",
]
SHELL_PLUS_MODEL_ALIASES = {
    "accounts": {"User": "U", "Company": "Co"},
    "catalog": {"Product": "P", "Fabric": "Fab"},
    "orders": {"Order": "O"},
}
GRAPH_MODELS = {"all_applications": False, "group_models": True, "app_labels": [a.split(".")[-1] for a in LOCAL_APPS]}
RUNSERVER_PLUS_PRINT_SQL_TRUNCATE = 1000
