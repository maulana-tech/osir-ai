"""JSON API for the Next.js UI (``web/``), mounted at ``/api/web/``.

Only the browser session authenticates here (``WebSessionAuth``: Django
session + CSRF). Everything an external agent may also need lives in the
Agent API at ``/api/v1/``, which the UI calls too; this API holds what is
UI-only: navigation, workspace membership, and page data that the
server-rendered templates used to assemble in views.
"""

from __future__ import annotations

from ninja import NinjaAPI

from apps.api.auth import WebSessionAuth

from .routers.account import router as account_router
from .routers.admin import org_router
from .routers.admin import router as admin_router
from .routers.analytics import router as analytics_router
from .routers.approvals import router as approvals_router
from .routers.calendar import router as calendar_router
from .routers.channels import router as channels_router
from .routers.composer import router as composer_router
from .routers.inbox import router as inbox_router
from .routers.me import router as me_router
from .routers.media import org_router as media_org_router
from .routers.media import router as media_router
from .routers.workspaces import router as workspaces_router

api = NinjaAPI(
    title="Osir AI Web API",
    version="web",
    urls_namespace="web_api",
    auth=WebSessionAuth(),
    docs_url=None,
)

api.add_router("/me", me_router)
api.add_router("/workspaces", workspaces_router)
api.add_router("/workspaces", calendar_router)
api.add_router("/workspaces", inbox_router)
api.add_router("/workspaces", analytics_router)
api.add_router("/workspaces", channels_router)
api.add_router("/workspaces", admin_router)
api.add_router("/workspaces", approvals_router)
api.add_router("/workspaces", media_router)
api.add_router("/workspaces", composer_router)
api.add_router("/org", org_router)
api.add_router("/org", media_org_router)
api.add_router("/me", account_router)
