"""Django authentication backend for the admin, built on `directory.py`."""

from django.contrib.auth.backends import ModelBackend


class DirectoryBackend(ModelBackend):
    """Development: plain model login. Replace with a `directory.verify` check per client."""
