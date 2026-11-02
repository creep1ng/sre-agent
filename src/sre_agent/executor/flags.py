"""flag.set (#724): the demo's fault flags, through the flag listener on the OTel demo instance.

The executor reaches the listener (`scripts/otel_demo/mcp_guest.py serve-flags`) over the link
`connect-mcp` forwards through SSM, with the listener's own token; it holds no AWS credential and
runs no command on the instance. The listener writes only the fault flags its manifest declares,
and only back to their baseline variant, so this client cannot turn a fault on either.
"""

from __future__ import annotations

from typing import Any

import httpx

from sre_agent.executor.catalog import EnrolledService
from sre_agent.executor.operations import ExecutionError, Intent


class FlagClient:
    def __init__(self, client: httpx.AsyncClient, base_url: str | None, token: str | None) -> None:
        self._client = client
        self._base = (base_url or "").rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}

    @property
    def configured(self) -> bool:
        return bool(self._base and self._headers)

    async def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        if not self.configured:
            raise ExecutionError(
                503, "flags_unavailable", "the demo's flag listener is not configured", True
            )
        try:
            response = await self._client.request(
                method, self._base + path, json=body, headers=self._headers, timeout=30
            )
        except httpx.HTTPError:  # the tunnel or the listener is down; nothing was written
            raise ExecutionError(
                503, "flags_unavailable", "the demo's flag listener did not answer", True
            ) from None
        if response.status_code != 200:
            raise ExecutionError(
                502, "execution_failed", f"the flag listener answered {response.status_code}"
            )
        return response.json()

    async def variants(self) -> dict[str, str]:
        """The current variant of every flag the listener may write."""
        body = await self._call("GET", "/flags")
        return {str(name): str(variant) for name, variant in body["flags"].items()}

    async def set(
        self, service: EnrolledService, flag: str, variant: str, intent: Intent
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        if variant not in service.flags.get(flag, ()):
            allowed = ", ".join(f"{name}={'|'.join(v)}" for name, v in service.flags.items())
            raise ExecutionError(
                422, "flag_not_allowed", f"'{service.service}' may set only {allowed}"
            )
        current = (await self.variants()).get(flag)
        if current is None:
            raise ExecutionError(422, "flag_not_allowed", f"the demo does not offer '{flag}'")
        before = {"flag": flag, "variant": current}
        if current == variant:
            return "already_at_target", before, before
        await intent()
        written = await self._call("PUT", f"/flags/{flag}", {"variant": variant})
        return "flag_set", before, {"flag": flag, "variant": str(written["variant"])}
