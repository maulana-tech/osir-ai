from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods


def health_check(request):
    """Health check endpoint at /health/."""
    return JsonResponse({"status": "ok"})


@login_required
def dashboard(request):
    """``/`` — land in the console: the last workspace's calendar, else the workspace list."""
    from apps.members.models import WorkspaceMembership

    ws_id = request.user.last_workspace_id
    if (
        ws_id
        and WorkspaceMembership.objects.filter(
            user=request.user, workspace_id=ws_id, workspace__is_archived=False
        ).exists()
    ):
        return redirect(f"/w/{ws_id}/calendar")
    return redirect("/org/workspaces")


@login_required
@require_http_methods(["GET", "POST"])
def accept_terms(request):
    """Terms of Service acceptance page for social signup users."""
    if request.user.tos_accepted_at is not None:
        return redirect("/")

    if request.method == "POST":
        if request.POST.get("agree"):
            request.user.tos_accepted_at = timezone.now()
            request.user.save(update_fields=["tos_accepted_at"])
            return redirect("/")
        messages.error(request, "You must agree to the Terms of Service and Privacy Policy to continue.")

    return render(request, "account/accept_terms.html")


def logout_view(request):
    logout(request)
    return redirect("account_login")
