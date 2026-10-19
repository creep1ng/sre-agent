"""Publish and activate the demo Skills through the governed ControlService.

A clean install seeds principals, credentials and model aliases but no Skill, so
nothing can be granted or resolved on the Skills side of the console. Run in the
seed container after the ordinary seed, with this directory mounted at /setup and
demo/skills at /skills:

    docker compose run --rm -v ./scripts:/setup:ro -v ./demo/skills:/skills:ro \\
        -e AUDIT_HMAC_KEY seed python /setup/provision_skills_demo.py

Each manifest is published with a deterministic idempotency key and then set to
active with compare-and-set. Rerunning converges. A different Skill already
stored under the same id/version, or any refused step, fails closed: nothing is
overwritten or cleaned up. No grant is created; access stays an admin decision.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from provision_incident_workflow import build_service

SKILLS_DIR = Path(os.environ.get("DEMO_SKILLS_DIR", "/skills"))


def manifests() -> list[dict]:
    # Dependencies first: a manifest depending on another demo Skill sorts after it.
    loaded = [json.loads(path.read_text()) for path in sorted(SKILLS_DIR.glob("*/*.json"))]
    return sorted(loaded, key=lambda body: len(body["manifest"].get("dependencies", [])))


def _payload(response) -> dict:
    return json.loads(response.body) if response.body else {}


async def converge(service, bearer: str, body: dict) -> str:
    skill_id, version = body["skill_id"], body["version"]
    published = await service.publish_skill_version(
        body, bearer, f"setup-v1-skill-{skill_id}-{version}"
    )
    if published.status_code != 201:
        raise RuntimeError(f"{skill_id}@{version}: publish refused ({published.status_code})")
    status = await service.get_skill_status(skill_id, version, bearer)
    if status.status_code == 200 and _payload(status).get("status") != "active":
        # An admin deactivated this version on purpose; never undo that silently.
        raise RuntimeError(f"{skill_id}@{version}: deactivated by an admin, left inactive")
    if status.status_code == 404:
        # Published but never activated: the status contract only exposes active/inactive.
        stored = await service.get_skill_version(skill_id, version, bearer)
        if stored.status_code != 200:
            raise RuntimeError(f"{skill_id}@{version}: version unreadable ({stored.status_code})")
        changed = await service.replace_skill_status(
            skill_id,
            version,
            {"status": "active", "expected_updated_at": _payload(stored)["created_at"]},
            bearer,
        )
        if changed.status_code != 200:
            raise RuntimeError(f"{skill_id}@{version}: activation refused ({changed.status_code})")
    elif status.status_code != 200:
        raise RuntimeError(f"{skill_id}@{version}: status unreadable ({status.status_code})")
    confirmed = await service.get_skill_status(skill_id, version, bearer)
    if confirmed.status_code != 200 or _payload(confirmed).get("status") != "active":
        raise RuntimeError(f"{skill_id}@{version}: not active after activation")
    return f"{skill_id}@{version}"


async def main() -> int:
    from sre_agent.persistence.database import Database

    if not all(
        os.environ.get(name) for name in ("DATABASE_URL", "ADMIN_HUMAN_API_KEY", "AUDIT_HMAC_KEY")
    ):
        print("skills: database/admin/audit configuration required", file=sys.stderr)
        return 2
    try:
        bodies = manifests()
    except (OSError, ValueError, KeyError, AttributeError):
        print("skills: unreadable manifest under " + str(SKILLS_DIR), file=sys.stderr)
        return 2
    if not bodies:
        print("skills: no manifest found; mount demo/skills at " + str(SKILLS_DIR), file=sys.stderr)
        return 2
    db = Database(os.environ["DATABASE_URL"])
    bearer = "Bearer " + os.environ["ADMIN_HUMAN_API_KEY"]
    service = build_service(db, os.environ["AUDIT_HMAC_KEY"].encode())
    done = []
    try:
        for body in bodies:
            done.append(await converge(service, bearer, body))
    except RuntimeError as error:
        print("skills: " + str(error) + "; existing state kept, no cleanup", file=sys.stderr)
        return 1
    except Exception:
        # Third-party exception text may contain connection details or credentials.
        print("skills: unavailable; inspect the stack, then rerun", file=sys.stderr)
        return 1
    finally:
        await db.dispose()
    print("demo skills active: " + ", ".join(done) + "; no grant created")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
