"""``/organizations/api-keys/`` — the page now lives in the Next.js console."""

from __future__ import annotations

from django.urls import path

from apps.common.console import console

app_name = "api_keys"

urlpatterns = [
    path("", console("/org/api-keys"), name="list"),
]
