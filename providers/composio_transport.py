"""Send a provider's HTTP request through Composio's proxy.

Composio injects the connected account's OAuth token server-side and
returns the platform's response, so the provider code that builds URLs,
payloads and parses replies stays untouched: only the wire hop changes.
Binary uploads travel as base64 in ``binary_body``.
"""

from __future__ import annotations

import base64
import json as jsonlib
from typing import Any

import httpx

from .exceptions import APIError

PROXY_URL = "https://backend.composio.dev/api/v3.1/tools/execute/proxy"
PROXY_TIMEOUT = 120.0


def _form_pairs(files: dict | None) -> dict[str, Any]:
    """``files={k: (None, v)}`` is how providers send plain multipart fields; flatten them."""
    out: dict[str, Any] = {}
    for k, v in (files or {}).items():
        if isinstance(v, tuple) and len(v) >= 2 and v[0] is None:
            out[k] = v[1]
        else:
            raise APIError("File uploads via multipart are not supported through Composio; use a binary body")
    return out


def proxy_request(
    *,
    api_key: str,
    connected_account_id: str,
    method: str,
    url: str,
    headers: dict | None = None,
    params: dict | None = None,
    json: dict | None = None,
    data: dict | bytes | None = None,
    files: dict | None = None,
    platform: str = "",
) -> httpx.Response:
    headers = dict(headers or {})
    parameters = [{"name": k, "value": str(v), "type": "header"} for k, v in headers.items()]
    parameters += [{"name": k, "value": str(v), "type": "query"} for k, v in (params or {}).items() if v is not None]

    payload: dict[str, Any] = {
        "connected_account_id": connected_account_id,
        "endpoint": url,
        "method": method.upper(),
        "parameters": parameters,
    }
    if isinstance(data, bytes):
        payload["binary_body"] = {
            "base64": base64.b64encode(data).decode("ascii"),
            "content_type": headers.get("Content-Type", "application/octet-stream"),
        }
    else:
        body: dict[str, Any] = {}
        if json:
            body.update(json)
        if isinstance(data, dict):
            body.update(data)
        body.update(_form_pairs(files))
        if body:
            payload["body"] = body

    resp = httpx.post(PROXY_URL, json=payload, headers={"x-api-key": api_key}, timeout=PROXY_TIMEOUT)
    if resp.status_code >= 400:
        raise APIError(
            f"Composio proxy error {resp.status_code}: {resp.text[:500]}",
            status_code=resp.status_code,
            platform=platform,
            raw_response=_safe_json(resp),
        )

    envelope = _safe_json(resp)
    status = int(envelope.get("status") or 200)
    upstream_headers = {str(k): str(v) for k, v in (envelope.get("headers") or {}).items()}
    data_out = envelope.get("data")
    if data_out is None and envelope.get("binary_data"):
        content = httpx.get(envelope["binary_data"]["url"], timeout=PROXY_TIMEOUT).content
    elif isinstance(data_out, str | bytes):
        content = data_out.encode() if isinstance(data_out, str) else data_out
    else:
        content = jsonlib.dumps(data_out if data_out is not None else {}).encode()
        upstream_headers.setdefault("content-type", "application/json")

    # Rebuild the platform's reply so callers see exactly what a direct call returns.
    return httpx.Response(
        status_code=status,
        headers=upstream_headers,
        content=content,
        request=httpx.Request(method.upper(), url),
    )


def _safe_json(resp: httpx.Response) -> dict:
    try:
        body = resp.json()
        return body if isinstance(body, dict) else {}
    except ValueError:
        return {}
