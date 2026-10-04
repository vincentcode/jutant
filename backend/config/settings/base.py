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
        env("DATABASE_URL", "postgres://jutant:jutant@localhost:5432/jutant")
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

STATIC_URL = "admin-static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Jutant ------------------------------------------------------------------

JUTANT_PACK_PATH = BASE_DIR / env("JUTANT_PACK_PATH", "packs/banking")
JUTANT_CALLER_SECRET = env("JUTANT_CALLER_SECRET", "change-me")
JUTANT_SESSION_SECRET = env("JUTANT_SESSION_SECRET", "change-me-too")
JUTANT_SESSION_TTL_MIN = int(env("JUTANT_SESSION_TTL_MIN", "480"))
JUTANT_CORS_ORIGINS = [o for o in env("JUTANT_CORS_ORIGINS", "").split(",") if o]

JUTANT_LLM_PROVIDER = env("JUTANT_LLM_PROVIDER", "ollama")
JUTANT_LLM_MODEL = env("JUTANT_LLM_MODEL", "qwen2.5:7b")
JUTANT_LLM_BASE_URL = env("JUTANT_LLM_BASE_URL", "http://localhost:11434")
JUTANT_LLM_NUM_CTX = int(env("JUTANT_LLM_NUM_CTX", "8192"))
JUTANT_LLM_TEMPERATURE = float(env("JUTANT_LLM_TEMPERATURE", "0.1"))
JUTANT_LLM_TIMEOUT_S = int(env("JUTANT_LLM_TIMEOUT_S", "300"))
JUTANT_EMBED_MODEL = env("JUTANT_EMBED_MODEL", "nomic-embed-text")
JUTANT_EMBED_DIM = int(env("JUTANT_EMBED_DIM", "768"))

JUTANT_MAX_STEPS = int(env("JUTANT_MAX_STEPS", "4"))
JUTANT_HISTORY_LIMIT = int(env("JUTANT_HISTORY_LIMIT", "6"))
JUTANT_MAX_CONCURRENT_GENERATIONS = int(env("JUTANT_MAX_CONCURRENT_GENERATIONS", "2"))

JUTANT_MCP_URLS = {
    "documents": env("JUTANT_MCP_DOCUMENTS_URL", "http://localhost:8101/mcp"),
    "transactions": env("JUTANT_MCP_TRANSACTIONS_URL", "http://localhost:8102/mcp"),
    "services": env("JUTANT_MCP_SERVICES_URL", "http://localhost:8103/mcp"),
}
JUTANT_BANKING_ADAPTERS = env("JUTANT_BANKING_ADAPTERS", "fake")
