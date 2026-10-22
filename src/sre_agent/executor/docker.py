"""The fixed list of Docker Engine calls the executor makes, through docker-socket-proxy.

Every method maps to one endpoint of the `containers` or `images` family, the
only ones the proxy forwards. Nothing here builds a path from a request value
other than a container id the daemon itself returned or an image reference
the catalog composed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx


class DockerUnavailable(Exception):
    """The proxy or the daemon could not be reached, or the daemon failed."""


class DockerTimeout(Exception):
    """The daemon did not answer within the call timeout."""


class DockerInvalid(Exception):
    """The daemon (or the proxy, with 403) answered outside the expected contract."""


class DockerNotFound(Exception):
    """The container or image does not exist."""


class DockerClient:
    def __init__(self, client: httpx.AsyncClient, base_url: str, timeout: float = 30.0) -> None:
        self._client = client
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    async def _call(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        try:
            response = await self._client.request(
                method, self._base + path, params=params, json=body, timeout=self._timeout
            )
        except httpx.TimeoutException as error:
            raise DockerTimeout(path) from error
        except httpx.HTTPError as error:
            raise DockerUnavailable(path) from error
        if response.status_code == 404:
            raise DockerNotFound(path)
        if response.status_code >= 500:
            raise DockerUnavailable(f"{method} {path} -> {response.status_code}")
        if response.status_code not in expected:
            raise DockerInvalid(f"{method} {path} -> {response.status_code}")
        if "application/json" not in response.headers.get("content-type", ""):
            return None
        try:
            return response.json()
        except ValueError as error:
            raise DockerInvalid(f"{method} {path} -> non-JSON body") from error

    async def ping(self) -> None:
        await self._call("GET", "/_ping")

    async def list_containers(self, labels: Mapping[str, str]) -> list[dict[str, Any]]:
        filters = json.dumps({"label": [f"{key}={value}" for key, value in labels.items()]})
        rows = await self._call(
            "GET", "/containers/json", params={"all": "true", "filters": filters}
        )
        return list(rows) if isinstance(rows, list) else []

    async def inspect_container(self, container_id: str) -> dict[str, Any]:
        return dict(await self._call("GET", f"/containers/{container_id}/json"))

    async def inspect_image(self, reference: str) -> dict[str, Any]:
        return dict(await self._call("GET", f"/images/{reference}/json"))

    async def list_image_tags(self, repository: str) -> list[str]:
        filters = json.dumps({"reference": [repository]})
        images = await self._call("GET", "/images/json", params={"filters": filters})
        prefix = repository + ":"
        return sorted(
            {
                tag.removeprefix(prefix)
                for image in images or ()
                for tag in image.get("RepoTags") or ()
                if tag.startswith(prefix)
            }
        )

    async def create_container(self, name: str, body: Mapping[str, Any]) -> str:
        created = await self._call(
            "POST", "/containers/create", params={"name": name}, body=body, expected=(201,)
        )
        return str(created["Id"])

    async def start(self, container_id: str) -> None:
        await self._call("POST", f"/containers/{container_id}/start", expected=(204, 304))

    async def stop(self, container_id: str, grace_seconds: int = 10) -> None:
        await self._call(
            "POST",
            f"/containers/{container_id}/stop",
            params={"t": grace_seconds},
            expected=(204, 304),
        )

    async def restart(self, container_id: str, grace_seconds: int = 10) -> None:
        await self._call(
            "POST",
            f"/containers/{container_id}/restart",
            params={"t": grace_seconds},
            expected=(204,),
        )

    async def rename(self, container_id: str, name: str) -> None:
        await self._call(
            "POST", f"/containers/{container_id}/rename", params={"name": name}, expected=(204,)
        )

    async def remove(self, container_id: str) -> None:
        await self._call("DELETE", f"/containers/{container_id}", expected=(204,))
