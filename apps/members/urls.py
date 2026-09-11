from django.urls import path

from apps.common.console import console

from . import views

app_name = "members"

urlpatterns = [
    path("", console("/org/members"), name="list"),
    # Still linked from the (Django-rendered) client-portal admin page.
    path("invite/<uuid:invitation_id>/resend/", console("/org/members"), name="resend_invite"),
    path("invite/<uuid:invitation_id>/revoke/", console("/org/members"), name="revoke_invite"),
    path("invite/<str:token>/accept/", views.accept_invite, name="accept_invite"),
]
