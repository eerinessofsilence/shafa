from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi.testclient import TestClient


def async_dependency(value: Any):
    async def _dependency():
        return value

    return _dependency


class SyncASGITestClient:
    def __init__(self, app, *, base_url: str = "http://testserver") -> None:
        self._app = app
        self._base_url = base_url
        self._cookies = httpx.Cookies()
        self.headers: dict[str, str] = {}
        self._websocket_client: TestClient | None = None

    async def _request_async(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        request_headers = dict(self.headers)
        if "headers" in kwargs and kwargs["headers"] is not None:
            request_headers.update(kwargs["headers"])
        kwargs["headers"] = request_headers

        transport = httpx.ASGITransport(app=self._app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=self._base_url,
            cookies=self._cookies,
            follow_redirects=True,
        ) as client:
            response = await client.request(method, url, **kwargs)
            self._cookies.update(response.cookies)
            return response

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        return asyncio.run(self._request_async(method, url, **kwargs))

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def options(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("OPTIONS", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)

    def websocket_connect(self, url: str, **kwargs: Any):
        if self._websocket_client is None:
            self._websocket_client = TestClient(self._app)
        return self._websocket_client.websocket_connect(url, **kwargs)

    def close(self) -> None:
        if self._websocket_client is not None:
            self._websocket_client.close()
            self._websocket_client = None
