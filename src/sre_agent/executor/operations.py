"""The two named operations: validate everything, write once, verify, report.

A rollback creates the replacement container before it touches the running
one, so a bad image or configuration fails with nothing changed. If the
replacement does not come up healthy, the old container gets its name back
and is started again: the service is never left without a container.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from sre_agent.executor.catalog import EnrolledService
from sre_agent.executor.docker import DockerClient, DockerNotFound

logger = logging.getLogger(__name__)
COMPOSE = "com.docker.compose."
EXECUTION_LABEL = "io.sre-agent.deploy-executor.execution"
Intent = Callable[[], Awaitable[None]]


class ExecutionError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def container_view(inspect: dict[str, Any]) -> dict[str, Any]:
    state = inspect.get("State") or {}
    health = state.get("Health") or {}
    return {
        "container_id": inspect["Id"],
        "name": str(inspect["Name"]).lstrip("/"),
        "image": inspect["Config"]["Image"],
        "state": state.get("Status"),
        "health": health.get("Status") if isinstance(health, dict) else None,
        "started_at": state.get("StartedAt"),
    }


class Operations:
    def __init__(
        self, docker: DockerClient, own_container: str | None, settle_seconds: float = 30.0
    ) -> None:
        self._docker = docker
        self._own_container = own_container
        self._own_project: str | None = None
        self._settle = settle_seconds

    async def find(self, service: EnrolledService) -> dict[str, Any]:
        """The one container of the service, inspected; 409 when there is none or several."""
        project = service.compose_project or await self._project()
        labels = {COMPOSE + "project": project, COMPOSE + "service": service.compose_service}
        rows = [
            row
            for row in await self._docker.list_containers(labels)
            if (row.get("Labels") or {}).get(COMPOSE + "oneoff", "False") != "True"
        ]
        if not rows:
            raise ExecutionError(
                409, "container_not_found", f"no container runs '{service.service}' in '{project}'"
            )
        if len(rows) > 1:
            raise ExecutionError(
                409, "service_ambiguous", f"'{service.service}' has {len(rows)} containers"
            )
        return await self._docker.inspect_container(str(rows[0]["Id"]))

    async def available_tags(self, service: EnrolledService) -> list[str]:
        if service.image_repository is None:
            return []
        return await self._docker.list_image_tags(service.image_repository)

    async def restart(
        self, service: EnrolledService, intent: Intent
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        before = await self.find(service)
        await intent()
        await self._docker.restart(before["Id"])
        try:
            after = await self._settled(before["Id"])
        except RuntimeError as error:
            raise ExecutionError(502, "execution_failed", str(error)) from error
        return "restarted", container_view(before), container_view(after)

    async def rollback(
        self, service: EnrolledService, to_tag: str, execution_id: str, intent: Intent
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        before = await self.find(service)
        target = f"{service.image_repository}:{to_tag}"
        try:
            image = await self._docker.inspect_image(target)
        except DockerNotFound:
            raise ExecutionError(
                422, "image_tag_unknown", f"{target} is not present in the local image store"
            ) from None
        if before["Image"] == image["Id"] and (before.get("State") or {}).get("Running"):
            return "already_at_target", container_view(before), container_view(before)
        name = str(before["Name"]).lstrip("/")
        inherited = (await self._docker.inspect_image(str(before["Image"]))).get("Config") or {}
        await intent()
        new_id = await self._docker.create_container(
            f"{name}.next", self._clone(before, inherited, target, str(image["Id"]), execution_id)
        )
        try:
            await self._docker.stop(before["Id"])
            await self._docker.rename(before["Id"], f"{name}.previous")
            await self._docker.rename(new_id, name)
            await self._docker.start(new_id)
            after = await self._settled(new_id)
        except Exception as error:
            await self._recover(before["Id"], new_id, name)
            raise ExecutionError(
                502, "execution_failed", f"{target} did not come up; the previous container is back"
            ) from error
        await self._docker.remove(before["Id"])
        return "rolled_back", container_view(before), container_view(after)

    async def _project(self) -> str:
        if self._own_project is None:
            if not self._own_container:
                raise ExecutionError(
                    409, "container_not_found", "the executor's project is unknown"
                )
            own = await self._docker.inspect_container(self._own_container)
            self._own_project = str((own["Config"].get("Labels") or {})[COMPOSE + "project"])
        return self._own_project

    async def _settled(self, container_id: str) -> dict[str, Any]:
        """Running, and healthy when the image declares a healthcheck, within the settle window."""
        deadline = monotonic() + self._settle
        while True:
            inspect = await self._docker.inspect_container(container_id)
            state = inspect.get("State") or {}
            health = (state.get("Health") or {}).get("Status")
            if state.get("Running") and health in (None, "healthy"):
                return inspect
            if state.get("Status") in ("exited", "dead") or monotonic() > deadline:
                raise RuntimeError(f"container is {state.get('Status')}, health {health}")
            await asyncio.sleep(0.5)

    async def _recover(self, old_id: str, new_id: str, name: str) -> None:
        for step in (
            lambda: self._docker.stop(new_id),
            lambda: self._docker.remove(new_id),
            lambda: self._docker.rename(old_id, name),
            lambda: self._docker.start(old_id),
        ):
            try:
                await step()
            except Exception:  # best effort: report the failure, keep the previous container
                logger.exception("rollback recovery step failed for %s", name)

    @staticmethod
    def _clone(
        inspect: dict[str, Any],
        inherited: dict[str, Any],
        image: str,
        image_id: str,
        execution_id: str,
    ) -> dict[str, Any]:
        """The container's own configuration with the target image, nothing else.

        The daemon merges an image's environment, command, ports, volumes and
        healthcheck into every container created from it. Those values belong
        to the image being replaced, so they are dropped and the target image
        supplies its own; what the operator declared on the container stays.
        """
        config: dict[str, Any] = {}
        for key, value in inspect["Config"].items():
            if key in ("Hostname", "Image"):
                continue
            if key == "Env":
                value = [item for item in value or () if item not in (inherited.get("Env") or ())]
            elif key == "Labels":
                # Compose stamps built images with its own labels; the container's Compose
                # identity (project, service) stays with the container, whatever the image says.
                image_labels = inherited.get("Labels") or {}
                value = {
                    k: v
                    for k, v in (value or {}).items()
                    if k.startswith(COMPOSE) or image_labels.get(k) != v
                }
            elif value == inherited.get(key):
                continue
            config[key] = value
        labels = dict(config.get("Labels") or {})
        labels[EXECUTION_LABEL] = execution_id
        if COMPOSE + "image" in labels:
            labels[COMPOSE + "image"] = image_id
        config |= {"Image": image, "Labels": labels}
        host = dict(inspect["HostConfig"])
        covered = {bind.split(":")[1] for bind in host.get("Binds") or () if ":" in bind}
        covered |= {mount["Target"] for mount in host.get("Mounts") or ()}
        # Anonymous volumes keep their data: bind them by name where nothing else covers the path.
        host["Binds"] = list(host.get("Binds") or ()) + [
            f"{m['Name']}:{m['Destination']}" + ("" if m.get("RW", True) else ":ro")
            for m in inspect.get("Mounts") or ()
            if m.get("Type") == "volume" and m["Destination"] not in covered
        ]
        short_id = inspect["Id"][:12]
        endpoints = {
            network: {
                key: value
                for key, value in {
                    "Aliases": [a for a in settings.get("Aliases") or () if a != short_id],
                    "IPAMConfig": settings.get("IPAMConfig"),
                    "Links": settings.get("Links"),
                    "DriverOpts": settings.get("DriverOpts"),
                }.items()
                if value
            }
            for network, settings in (inspect["NetworkSettings"].get("Networks") or {}).items()
        }
        return {**config, "HostConfig": host, "NetworkingConfig": {"EndpointsConfig": endpoints}}
