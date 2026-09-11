"""``apps.composer.unsplash``: search proxy and import into the media library.

Unsplash HTTP traffic is mocked at ``apps.composer.unsplash.httpx`` so no
network is involved.
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.composer import unsplash
from apps.media_library.models import MediaAsset
from apps.workspaces.models import Workspace


def _response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data or {})
    return resp


def _photo(photo_id="abc123"):
    return {
        "id": photo_id,
        "thumb": f"https://images.unsplash.com/{photo_id}?w=400",
        "full": f"https://images.unsplash.com/{photo_id}?w=1080",
        "width": 4000,
        "height": 3000,
        "color": "#c0ffee",
        "alt": "A cup of coffee",
        "photographer": "Brigitte Tohm",
        "photographer_url": "https://unsplash.com/@brigittetohm",
        "photo_url": f"https://unsplash.com/photos/{photo_id}",
        "download_location": f"https://api.unsplash.com/photos/{photo_id}/download",
    }


@pytest.fixture
def key(settings):
    settings.UNSPLASH_ACCESS_KEY = "test-key"


def _raises(status, fn, *args):
    with pytest.raises(unsplash.UnsplashError) as exc:
        fn(*args)
    assert exc.value.status == status
    return exc.value


class TestSearch:
    def test_503_without_api_key(self, settings):
        settings.UNSPLASH_ACCESS_KEY = ""
        assert "UNSPLASH_ACCESS_KEY" in _raises(503, unsplash.search, "coffee").message

    def test_missing_query_400(self, key):
        _raises(400, unsplash.search, "  ")

    @patch("apps.composer.unsplash.httpx.get")
    def test_results_trimmed_to_ui_fields(self, mock_get, key):
        mock_get.return_value = _response(
            json_data={
                "total": 1,
                "results": [
                    {
                        "id": "abc123",
                        "width": 4000,
                        "height": 3000,
                        "color": "#c0ffee",
                        "alt_description": "A cup of coffee",
                        "description": None,
                        "urls": {"small": "s", "regular": "r", "raw": "x", "full": "y", "thumb": "z"},
                        "user": {"name": "Brigitte Tohm", "username": "bt", "links": {"html": "u"}},
                        "links": {"html": "h", "download_location": "d"},
                    }
                ],
            }
        )
        data = unsplash.search("coffee")
        assert data["total"] == 1
        assert set(data["results"][0]) == set(_photo())
        assert data["results"][0]["alt"] == "A cup of coffee"
        # The key must be sent as a Client-ID header, not a query param.
        assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Client-ID test-key"

    @patch("apps.composer.unsplash.httpx.get")
    def test_rate_limit_maps_to_429(self, mock_get, key):
        mock_get.return_value = _response(status_code=429)
        _raises(429, unsplash.search, "coffee")

    @patch("apps.composer.unsplash.httpx.get")
    @pytest.mark.parametrize("body", [[], None, "oops"])
    def test_non_object_body_maps_to_502(self, mock_get, key, body):
        resp = MagicMock()
        resp.status_code = 200
        resp.json = MagicMock(return_value=body)
        mock_get.return_value = resp
        _raises(502, unsplash.search, "coffee")


def _stream_cm(*, status_code=200, content=b"jpeg-bytes", content_type="image/jpeg", content_length=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"content-type": content_type}
    if content_length is not None:
        resp.headers["content-length"] = content_length
    resp.iter_bytes = MagicMock(return_value=[content])
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _client(*, get_side_effect=(), stream_side_effect=()):
    """Patch the pooled httpx.Client: ``get`` registers the download, ``stream`` yields the bytes."""
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get = MagicMock(side_effect=list(get_side_effect))
    client.stream = MagicMock(side_effect=list(stream_side_effect))
    return patch("apps.composer.unsplash.httpx.Client", return_value=client), client


def _ok_client(photo_id="abc123"):
    return _client(
        get_side_effect=[_response(json_data={"url": f"https://images.unsplash.com/{photo_id}?dl=1"})],
        stream_side_effect=[_stream_cm()],
    )


@pytest.fixture
def ws(db, organization, settings, tmp_path, key):
    settings.MEDIA_ROOT = str(tmp_path)
    return Workspace.objects.create(organization=organization, name="WS")


@pytest.mark.django_db
class TestImport:
    def test_503_without_api_key(self, ws, org_owner, settings):
        settings.UNSPLASH_ACCESS_KEY = ""
        _raises(503, unsplash.import_photos, ws, org_owner, [_photo()])

    def test_creates_asset_with_attribution(self, ws, org_owner):
        patcher, _ = _ok_client()
        with patcher:
            assets, failed = unsplash.import_photos(ws, org_owner, [_photo()])
        asset = MediaAsset.objects.get(workspace=ws)
        assert assets == [asset] and failed == 0
        assert asset.source == "unsplash" and asset.organization == ws.organization
        assert asset.source_url == "https://unsplash.com/photos/abc123"
        assert asset.attribution == "Photo by Brigitte Tohm on Unsplash"
        assert asset.media_type == MediaAsset.MediaType.IMAGE

    @pytest.mark.parametrize(
        "bad", [{"download_location": "https://evil.example.com/steal"}, {"download_location": None, "full": None}]
    )
    def test_rejects_bad_download_location_before_any_request(self, ws, org_owner, bad):
        patcher, client = _client()
        with patcher:
            _raises(502, unsplash.import_photos, ws, org_owner, [{**_photo(), **bad}])
        assert MediaAsset.objects.count() == 0
        client.get.assert_not_called()

    def test_null_attribution_fields_do_not_crash_save(self, ws, org_owner):
        patcher, _ = _ok_client()
        with patcher:
            unsplash.import_photos(ws, org_owner, [{**_photo(), "photo_url": None, "photographer": None, "alt": None}])
        asset = MediaAsset.objects.get(workspace=ws)
        assert (asset.source_url, asset.alt_text, asset.attribution) == ("", "", "Photo by Unknown on Unsplash")

    def test_rejects_non_unsplash_image_url(self, ws, org_owner):
        # Registration succeeds but points the byte download somewhere else.
        patcher, client = _client(get_side_effect=[_response(json_data={"url": "https://evil.example.com/img.jpg"})])
        with patcher:
            _raises(
                502, unsplash.import_photos, ws, org_owner, [{**_photo(), "full": "https://evil.example.com/i.jpg"}]
            )
        assert MediaAsset.objects.count() == 0
        # The allowlist must reject before any image bytes are streamed.
        client.stream.assert_not_called()

    def test_oversized_image_rejected_by_declared_length(self, ws, org_owner):
        patcher, _ = _client(
            get_side_effect=[_response(json_data={"url": "https://images.unsplash.com/abc?dl=1"})],
            stream_side_effect=[_stream_cm(content_length=str(20 * 1024 * 1024))],
        )
        with patcher:
            _raises(502, unsplash.import_photos, ws, org_owner, [_photo()])
        assert MediaAsset.objects.count() == 0

    def test_quota_exceeded_413(self, ws, org_owner):
        from apps.media_library.quotas import StorageQuotaExceededError

        patcher, _ = _ok_client()
        with (
            patcher,
            patch(
                "apps.media_library.quotas.enforce_storage_quota",
                side_effect=StorageQuotaExceededError(used=10, limit=10, attempted=10),
            ),
        ):
            _raises(413, unsplash.import_photos, ws, org_owner, [_photo()])
        assert MediaAsset.objects.count() == 0

    def test_caps_photos_per_import(self, ws, org_owner):
        _raises(400, unsplash.import_photos, ws, org_owner, [_photo(f"p{i}") for i in range(11)])
