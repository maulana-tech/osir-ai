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

from .routers.me import router as me_router
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
