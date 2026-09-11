"""Invitation landing page (the team page itself lives in the Next.js console)."""

from django.shortcuts import redirect, render

from apps.workspaces.models import Workspace

from . import services
from .models import Invitation, OrgMembership


def _org_role_choices_for(membership):
    """Org-role options the *viewer* is allowed to assign.

    Only owners can grant the Admin role (mirrors the owner-only guard in
    ``services.create_invitation`` / ``services.update_member_org_role``), so
    non-owners only ever see Member — they never get offered a role the
    backend would reject. The backend checks remain as the defense-in-depth
    backstop; this is UX only.
    """
    choices = []
    if membership.org_role == OrgMembership.OrgRole.OWNER:
        choices.append((OrgMembership.OrgRole.ADMIN, "Admin"))
    choices.append((OrgMembership.OrgRole.MEMBER, "Member"))
    return choices


def accept_invite(request, token):
    """Accept an invitation (public - no login required for GET)."""
    try:
        invitation = Invitation.objects.select_related("organization", "invited_by").get(token=token)
    except Invitation.DoesNotExist:
        return render(request, "members/invite_expired.html", status=404)

    if invitation.is_expired or invitation.is_accepted:
        return render(request, "members/invite_expired.html")

    # Resolve workspace names for display
    ws_display = []
    for a in invitation.workspace_assignments:
        try:
            ws = Workspace.objects.get(id=a["workspace_id"])
            ws_display.append({"name": ws.name, "role": a.get("role", "viewer")})
        except Workspace.DoesNotExist:
            pass

    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next=/members/invite/{token}/accept/")

        try:
            services.accept_invitation(invitation, request.user)
        except ValueError as e:
            return render(
                request,
                "members/accept_invite.html",
                {
                    "invitation": invitation,
                    "ws_display": ws_display,
                    "error": str(e),
                },
            )

        # Redirect to first assigned workspace or home
        if request.user.last_workspace_id:
            return redirect("calendar:calendar", workspace_id=request.user.last_workspace_id)
        return redirect("/")

    # GET - store token in session for signup flow
    request.session["pending_invite_token"] = token

    return render(
        request,
        "members/accept_invite.html",
        {
            "invitation": invitation,
            "ws_display": ws_display,
            "accept_url": f"/members/invite/{token}/accept/",
        },
    )
