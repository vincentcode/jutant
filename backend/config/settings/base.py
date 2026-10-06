"""Settings shared by every environment."""

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Missing environment variable {name}")
    return value


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-key")
DEBUG = False
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "apps.identity",
    "apps.conversation",
    "apps.knowledge",
    "apps.playbooks",
    "apps.audit",
    "apps.evals",
    "ingestion",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", "postgres://jutant:jutant@127.0.0.1:5432/jutant")
    ),
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTHENTICATION_BACKENDS = [
    "apps.identity.backends.DirectoryBackend",
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/admin/static/"  # served by the API, under the admin mount (config/asgi.py)
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Jutant ------------------------------------------------------------------

JUTANT_PACK_PATH = BASE_DIR / env("JUTANT_PACK_PATH", "packs/banking")
JUTANT_CALLER_SECRET = env("JUTANT_CALLER_SECRET", "change-me")
JUTANT_SESSION_SECRET = env("JUTANT_SESSION_SECRET", "change-me-too")
JUTANT_SESSION_TTL_MIN = int(env("JUTANT_SESSION_TTL_MIN", "480"))

# Sign-in limits against password guessing: a username is locked after this many failures in
# the window, and an address after this many across all usernames.
JUTANT_LOGIN_MAX_FAILURES = int(env("JUTANT_LOGIN_MAX_FAILURES", "5"))
JUTANT_LOGIN_MAX_FAILURES_PER_IP = int(env("JUTANT_LOGIN_MAX_FAILURES_PER_IP", "20"))
JUTANT_LOGIN_WINDOW_MIN = int(env("JUTANT_LOGIN_WINDOW_MIN", "15"))

# How long data kept only for a while is kept (manage.py purge_expired deletes it).
JUTANT_UPLOAD_RETENTION_DAYS = int(env("JUTANT_UPLOAD_RETENTION_DAYS", "30"))
JUTANT_LOGIN_ATTEMPT_RETENTION_DAYS = int(env("JUTANT_LOGIN_ATTEMPT_RETENTION_DAYS", "7"))

# Tracing (OpenTelemetry, e.g. to Phoenix): off unless the endpoint is set. Tool arguments are
# always traced, masked as in the audit log. Prompts, replies, questions, answers and tool
# results are traced only with JUTANT_TRACE_CONTENT=true, and masked too.
JUTANT_TRACING_ENDPOINT = env("JUTANT_TRACING_ENDPOINT", "")  # http://phoenix:6006/v1/traces
JUTANT_TRACING_API_KEY = env("JUTANT_TRACING_API_KEY", "")
JUTANT_TRACING_SERVICE_NAME = env("JUTANT_TRACING_SERVICE_NAME", "jutant-api")
JUTANT_TRACING_PROJECT = env("JUTANT_TRACING_PROJECT", "jutant")
JUTANT_TRACE_CONTENT = env("JUTANT_TRACE_CONTENT", "false").lower() in ("1", "true", "yes")
# Proxies whose X-Forwarded-For is believed (comma-separated addresses or networks), such as
# the web container's nginx. Empty: the connecting address is the client's.
JUTANT_TRUSTED_PROXIES = [
    p.strip() for p in env("JUTANT_TRUSTED_PROXIES", "").split(",") if p.strip()
]
# Secure cookies are sent over HTTPS only; the development settings turn this off for http://localhost.
JUTANT_SESSION_COOKIE_SECURE = env("JUTANT_SESSION_COOKIE_SECURE", "true").lower() == "true"
JUTANT_CORS_ORIGINS = [o for o in env("JUTANT_CORS_ORIGINS", "").split(",") if o]

JUTANT_LLM_PROVIDER = env("JUTANT_LLM_PROVIDER", "ollama")
JUTANT_LLM_MODEL = env("JUTANT_LLM_MODEL", "qwen2.5:7b")
JUTANT_LLM_BASE_URL = env("JUTANT_LLM_BASE_URL", "http://localhost:11434")
JUTANT_LLM_NUM_CTX = int(env("JUTANT_LLM_NUM_CTX", "8192"))
JUTANT_LLM_TEMPERATURE = float(env("JUTANT_LLM_TEMPERATURE", "0.1"))
JUTANT_LLM_TIMEOUT_S = int(env("JUTANT_LLM_TIMEOUT_S", "300"))
JUTANT_EMBED_MODEL = env("JUTANT_EMBED_MODEL", "nomic-embed-text")
JUTANT_EMBED_DIM = int(env("JUTANT_EMBED_DIM", "768"))
# Task prefixes the embedding model was trained with (these are nomic-embed-text's); empty for
# models that use none. Changing them, or the model, needs `manage.py reindex`.
JUTANT_EMBED_QUERY_PREFIX = env("JUTANT_EMBED_QUERY_PREFIX", "search_query: ")
JUTANT_EMBED_DOCUMENT_PREFIX = env("JUTANT_EMBED_DOCUMENT_PREFIX", "search_document: ")
JUTANT_EMBED_ROUTE_PREFIX = env("JUTANT_EMBED_ROUTE_PREFIX", "classification: ")

# Routing by meaning decides only when the question is this similar to a feature's examples,
# and this far ahead of the next feature; otherwise the model chooses. Measured on the evals.
JUTANT_ROUTE_MIN_SIMILARITY = float(env("JUTANT_ROUTE_MIN_SIMILARITY", "0.80"))
JUTANT_ROUTE_MIN_MARGIN = float(env("JUTANT_ROUTE_MIN_MARGIN", "0.05"))

JUTANT_MAX_STEPS = int(env("JUTANT_MAX_STEPS", "4"))
JUTANT_HISTORY_LIMIT = int(env("JUTANT_HISTORY_LIMIT", "6"))
JUTANT_MAX_CONCURRENT_GENERATIONS = int(env("JUTANT_MAX_CONCURRENT_GENERATIONS", "2"))

JUTANT_MCP_URLS = {
    "documents": env("JUTANT_MCP_DOCUMENTS_URL", "http://localhost:8101/mcp"),
    "transactions": env("JUTANT_MCP_TRANSACTIONS_URL", "http://localhost:8102/mcp"),
    "services": env("JUTANT_MCP_SERVICES_URL", "http://localhost:8103/mcp"),
}
JUTANT_BANKING_ADAPTERS = env("JUTANT_BANKING_ADAPTERS", "fake")
