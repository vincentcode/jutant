from .base import *  # noqa: F403
from .base import env

DEBUG = False
SECRET_KEY = env("DJANGO_SECRET_KEY")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
