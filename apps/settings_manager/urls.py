from django.urls import path

from apps.common.console import console

app_name = "settings_manager"

urlpatterns = [
    path("", console("/me/account"), name="index"),
]
