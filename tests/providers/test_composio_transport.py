"""Composio proxy: a provider with proxy credentials never sends a token itself, and
the platform's reply comes back looking exactly like a direct response."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import httpx
import pytest

from providers.exceptions import APIError, RateLimitError
from providers.linkedin_personal import LinkedInPersonalProvider

PROXY_CREDS = {
    "client_id": "x",
    "client_secret": "y",
    "composio_api_key": "ck",
    "composio_connected_account_id": "ca_1",
}


def _proxy_reply(status=200, data=None, headers=None):
    body = {"status": status, "data": data if data is not None else {}, "headers": headers or {}}
    return httpx.Response(200, json=body, request=httpx.Request("POST", "https://backend.composio.dev/x"))


def test_request_goes_through_proxy_with_headers_query_and_json_body():
    provider = LinkedInPersonalProvider(PROXY_CREDS)
    with patch(
        "providers.composio_transport.httpx.post", return_value=_proxy_reply(data={"id": "urn:li:share:1"})
    ) as post:
        resp = provider._request(
            "POST",
            "https://api.linkedin.com/rest/posts",
            access_token="should-not-be-sent",
            headers={"LinkedIn-Version": "202409"},
            params={"q": "author"},
            json={"commentary": "hi"},
        )

    assert resp.status_code == 200 and resp.json() == {"id": "urn:li:share:1"}
    payload = post.call_args.kwargs["json"]
    assert payload["connected_account_id"] == "ca_1"
    assert payload["endpoint"] == "https://api.linkedin.com/rest/posts"
    assert payload["method"] == "POST"
    assert payload["body"] == {"commentary": "hi"}
    assert {"name": "LinkedIn-Version", "value": "202409", "type": "header"} in payload["parameters"]
    assert {"name": "q", "value": "author", "type": "query"} in payload["parameters"]
    assert not any(p["name"].lower() == "authorization" for p in payload["parameters"])
    assert post.call_args.kwargs["headers"] == {"x-api-key": "ck"}


def test_binary_body_is_base64_encoded():
    provider = LinkedInPersonalProvider(PROXY_CREDS)
    with patch("providers.composio_transport.httpx.post", return_value=_proxy_reply(status=201)) as post:
        provider._request("PUT", "https://upload/x", headers={"Content-Type": "image/png"}, data=b"\x89PNG")
    payload = post.call_args.kwargs["json"]
    assert payload["binary_body"] == {"base64": base64.b64encode(b"\x89PNG").decode(), "content_type": "image/png"}
    assert "body" not in payload


def test_upstream_errors_map_to_provider_exceptions():
    provider = LinkedInPersonalProvider(PROXY_CREDS)
    limited = _proxy_reply(status=429, headers={"Retry-After": "7"})
    with patch("providers.composio_transport.httpx.post", return_value=limited), pytest.raises(RateLimitError) as exc:
        provider._request("GET", "https://api.linkedin.com/v2/me")
    assert exc.value.retry_after == 7

    forbidden = _proxy_reply(status=403, data={"message": "no"})
    with patch("providers.composio_transport.httpx.post", return_value=forbidden), pytest.raises(APIError) as exc2:
        provider._request("GET", "https://api.linkedin.com/v2/me")
    assert exc2.value.status_code == 403


def test_composio_level_failure_is_an_api_error():
    provider = LinkedInPersonalProvider(PROXY_CREDS)
    bad = httpx.Response(401, json={"error": {"message": "bad key"}}, request=httpx.Request("POST", "https://x"))
    with (
        patch("providers.composio_transport.httpx.post", return_value=bad),
        pytest.raises(APIError, match="Composio proxy error 401"),
    ):
        provider._request("GET", "https://api.linkedin.com/v2/me")


def test_without_proxy_credentials_the_direct_path_sends_the_bearer():
    provider = LinkedInPersonalProvider({"client_id": "x", "client_secret": "y"})
    client = MagicMock()
    client.__enter__.return_value = client
    client.request.return_value = httpx.Response(200, json={}, request=httpx.Request("GET", "https://x"))
    with patch("providers.base.httpx.Client", return_value=client):
        provider._request("GET", "https://api.linkedin.com/v2/me", access_token="tok")
    assert client.request.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"
