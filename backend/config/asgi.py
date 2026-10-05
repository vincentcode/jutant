"""Django ASGI app, mounted by the API at /admin.

The admin's own CSS and JavaScript are served from here too, so the admin needs no separate
static file server (they are only a few hundred kilobytes and used by operations staff only).
"""

import os

from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
application = ASGIStaticFilesHandler(get_asgi_application())
