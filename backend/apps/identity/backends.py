"""Django admin login, checked against the client's directory through `directory.py`."""

from django.contrib.auth.backends import ModelBackend

from apps.identity import directory, services


class DirectoryBackend(ModelBackend):
    """Logs in through the directory, then keeps the Staff row in step with it.

    Permissions still come from Django (`ModelBackend`), so admin access is granted per user.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None
        attrs = directory.verify(username, password)
        if attrs is None:
            return None
        staff = services.sync_from_directory(username=username, directory_attrs=attrs)
        user = staff.user
        return user if self.user_can_authenticate(user) else None
