from django.urls import path

from apps.common.console import console

app_name = "notifications"

urlpatterns = [
    path("", console("/me/notifications"), name="list"),
    path("preferences/", console("/me/notifications/preferences"), name="preferences"),
]
