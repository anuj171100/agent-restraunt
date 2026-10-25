from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx

# Body is stored after httpx has already decoded it, so these describe the
# wire framing and must not be replayed onto the plain text.
_WIRE_HEADERS = {"content-encoding", "content-length", "transfer-encoding"}


def replay_headers(headers: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key.lower() not in _WIRE_HEADERS}


def field_mask(headers: dict[str, str] | None) -> str:
    if not headers:
        return ""
    for key, value in headers.items():
        if key.lower() == "x-goog-fieldmask":
            return value.strip()
    return ""


class HttpCache:
    """Store every HTTP response under cache/, keyed by method + URL + field mask + body."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        field_mask: str = "",
    ) -> Path:
        raw = f"{method.upper()}\n{url}\n{field_mask}\n".encode() + (body or b"")
        digest = hashlib.sha256(raw).hexdigest()
        return self.root / f"{digest}.json"

    def get(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        field_mask: str = "",
    ) -> dict[str, Any] | None:
        path = self.path_for(method, url, body, field_mask)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put(
        self,
        method: str,
        url: str,
        body: bytes | None,
        status_code: int,
        headers: dict[str, str],
        text: str,
        field_mask: str = "",
    ) -> Path:
        path = self.path_for(method, url, body, field_mask)
        payload = {
            "method": method.upper(),
            "url": url,
            "status_code": status_code,
            "headers": replay_headers(headers),
            "text": text,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


class CachedClient:
    def __init__(self, cache: HttpCache, timeout: float = 30.0) -> None:
        self.cache = cache
        self.timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: Any = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        body = None if json_body is None else json.dumps(json_body, ensure_ascii=False).encode()
        mask = field_mask(headers)
        cached = self.cache.get(method, url, body, mask)
        if cached is not None:
            return httpx.Response(
                status_code=cached["status_code"],
                headers=replay_headers(cached.get("headers") or {}),
                text=cached.get("text") or "",
                request=httpx.Request(method, url),
            )

        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.request(
                method,
                url,
                headers=headers,
                content=body,
                params=params,
            )

        self.cache.put(
            method,
            url,
            body,
            response.status_code,
            dict(response.headers),
            response.text,
            mask,
        )
        return response

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)
