"""Media library through the web API."""

from __future__ import annotations

import io
import json
import secrets
from unittest.mock import patch

import pytest
from PIL import Image

from apps.media_library.models import MediaAsset, MediaFolder


def _send(client, method, path, data=None, **extra):
    token = secrets.token_hex(16)
    client.cookies["csrftoken"] = token
    kwargs = {"HTTP_X_CSRFTOKEN": token, **extra}
    if data is not None:
        kwargs.update(data=json.dumps(data), content_type="application/json")
    return getattr(client, method)(path, **kwargs)


def _png(name="a.png"):
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "black").save(buf, "PNG")
    buf.seek(0)
    buf.name = name
    return buf


@pytest.mark.django_db
class TestWorkspaceLibrary:
    def test_upload_list_detail_star_tags_move_delete(self, member_client, workspace):
        token = secrets.token_hex(16)
        member_client.cookies["csrftoken"] = token
        with patch("apps.webapi.routers.media.process_media_asset"):
            r = member_client.post(
                f"/api/web/workspaces/{workspace.id}/media/upload",
                {"files": [_png(), _png("b.png")]},
                HTTP_X_CSRFTOKEN=token,
            )
        assert r.status_code == 200, r.content
        results = r.json()["results"]
        assert [x["ok"] for x in results] == [True, True]
        asset_id = results[0]["asset"]["id"]

        body = member_client.get(f"/api/web/workspaces/{workspace.id}/media?sort=name").json()
        assert body["total"] == 2 and body["assets"][0]["filename"] == "a.png"
        assert body["can"]["upload_media"] is True and body["folders"] == []

        r = _send(member_client, "post", f"/api/web/workspaces/{workspace.id}/media/folders", {"name": "Brand"})
        assert r.status_code == 200
        folder_id = r.json()["id"]
        assert r.json()["folders"][0]["name"] == "Brand"

        assert _send(member_client, "post", f"/api/web/workspaces/{workspace.id}/media/{asset_id}/star").json() == {
            "is_starred": True
        }
        r = _send(
            member_client,
            "put",
            f"/api/web/workspaces/{workspace.id}/media/{asset_id}/tags",
            {"tags": ["hero", " hero "]},
        )
        assert r.status_code == 200 and r.json()["tags"] == ["hero"]
        assert member_client.get(f"/api/web/workspaces/{workspace.id}/media/tags?q=he").json()["tags"] == ["hero"]

        r = _send(
            member_client, "post", f"/api/web/workspaces/{workspace.id}/media/{asset_id}/move", {"folder_id": folder_id}
        )
        assert r.status_code == 200 and r.json()["folder_id"] == folder_id
        assert member_client.get(f"/api/web/workspaces/{workspace.id}/media?folder={folder_id}").json()["total"] == 1

        detail = member_client.get(f"/api/web/workspaces/{workspace.id}/media/{asset_id}").json()
        assert detail["asset"]["is_starred"] is True and detail["download_url"].endswith("/download/")

        r = _send(
            member_client, "patch", f"/api/web/workspaces/{workspace.id}/media/folders/{folder_id}", {"name": "  "}
        )
        assert r.status_code == 400
        assert (
            _send(member_client, "delete", f"/api/web/workspaces/{workspace.id}/media/folders/{folder_id}").status_code
            == 200
        )
        assert MediaAsset.objects.get(id=asset_id).folder_id is None
        assert not MediaFolder.objects.filter(id=folder_id).exists()

        assert _send(member_client, "delete", f"/api/web/workspaces/{workspace.id}/media/{asset_id}").status_code == 200
        assert not MediaAsset.objects.filter(id=asset_id).exists()

    def test_edit_creates_version(self, member_client, workspace):
        token = secrets.token_hex(16)
        member_client.cookies["csrftoken"] = token
        with patch("apps.webapi.routers.media.process_media_asset"):
            asset_id = member_client.post(
                f"/api/web/workspaces/{workspace.id}/media/upload", {"files": [_png()]}, HTTP_X_CSRFTOKEN=token
            ).json()["results"][0]["asset"]["id"]
        with (
            patch("apps.media_library.services.process_image_edit", create=True),
            patch("apps.media_library.tasks.process_image_edit"),
        ):
            r = _send(
                member_client,
                "post",
                f"/api/web/workspaces/{workspace.id}/media/{asset_id}/edit",
                {"rotate": 90, "crop_x": 0, "crop_y": 0, "crop_width": 10, "crop_height": 10},
            )
        assert r.status_code == 200, r.content
        assert r.json()["number"] == 1 and "Rotated 90deg" in r.json()["description"]
        r = _send(member_client, "post", f"/api/web/workspaces/{workspace.id}/media/{asset_id}/edit", {"rotate": 45})
        assert r.status_code == 400

    def test_shared_library_admin(self, member_client):
        token = secrets.token_hex(16)
        member_client.cookies["csrftoken"] = token
        with patch("apps.webapi.routers.media.process_media_asset"):
            r = member_client.post("/api/web/org/media/upload", {"files": [_png("s.png")]}, HTTP_X_CSRFTOKEN=token)
        assert r.status_code == 200, r.content
        asset_id = r.json()["results"][0]["asset"]["id"]
        body = member_client.get("/api/web/org/media").json()
        assert body["is_admin"] is True and body["assets"][0]["is_shared"] is True
        assert _send(member_client, "delete", f"/api/web/org/media/{asset_id}").status_code == 200
