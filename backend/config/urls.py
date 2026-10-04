"""Django serves the admin only; the product API is FastAPI (`api/`)."""

from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("", admin.site.urls),
]
