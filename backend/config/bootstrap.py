"""Set up Django for processes that do not start through Django itself.

The ORM only works after `django.setup()` has run. The API, the MCP servers and the workers
start on their own, so each imports this module before anything that touches the models.
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()
