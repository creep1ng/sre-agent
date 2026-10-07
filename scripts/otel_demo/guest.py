from __future__ import annotations

import base64
import re
from datetime import UTC, datetime
from pathlib import Path

from .common import DEMO_ENV, DIGESTS, MANIFEST, MAX_USER_DATA_BYTES, UPSTREAM, DemoError


def _manifest_pin(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    tag = re.search(r'^\s+tag:\s*["\']?([^"\'\s]+)', text, re.MULTILINE)
    commit = re.search(r'^\s+commit:\s*["\']?([0-9a-f]{40})', text, re.MULTILINE)
    if not tag or not commit:
        raise DemoError("demo manifest must pin an upstream tag and commit")
    return tag.group(1), commit.group(1)


def _digest_lock(path: Path) -> str:
    entries: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 2 or not re.fullmatch(r"sha256:[0-9a-f]{64}", fields[1]):
            raise DemoError("demo digest lock contains an invalid entry")
        entries.append(line)
    if not entries:
        raise DemoError("demo digest lock is empty")
    return "\n".join(entries) + "\n"


def build_user_data(
    *,
    expires_at: datetime,
    manifest_path: Path = MANIFEST,
    env_path: Path = DEMO_ENV,
    digest_path: Path = DIGESTS,
) -> str:
    """Embed pinned app data and arm persistent absolute expiry before network bootstrap."""
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        raise DemoError("expiry must include a timezone")
    expires = expires_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    tag, commit = _manifest_pin(manifest_path)
    env64 = base64.b64encode(env_path.read_bytes()).decode("ascii")
    digests64 = base64.b64encode(_digest_lock(digest_path).encode()).decode("ascii")
    script = f'''#!/bin/bash
set -Eeuo pipefail
exec > >(tee -a /var/log/otel-demo-bootstrap.log) 2>&1
install -d -m 0755 /opt/otel-demo
date -u +%Y-%m-%dT%H:%M:%SZ > /etc/otel-demo-created-at
printf '%s\\n' '{expires}' > /etc/otel-demo-deadline
cat >/etc/systemd/system/otel-demo-expire.service <<'UNIT'
[Unit]
Description=Expire temporary OTel Demo session
[Service]
Type=oneshot
ExecStart=/usr/sbin/shutdown -h now
UNIT
cat >/etc/systemd/system/otel-demo-expire.timer <<'UNIT'
[Unit]
Description=Absolute UTC OTel Demo deadline
[Timer]
OnCalendar={expires}
Persistent=true
Unit=otel-demo-expire.service
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now otel-demo-expire.timer
cat >/usr/local/sbin/otel-demo-set-deadline <<'EXTEND'
#!/bin/bash
set -Eeuo pipefail
exec 9>/run/lock/otel-demo-deadline.lock
flock -x 9
deadline="${{1:?UTC deadline required}}"
created="$(cat /etc/otel-demo-created-at)"
max="$(date -u -d "$created +12 hours" +%s)"
requested="$(date -u -d "$deadline" +%s)"
[[ "$requested" -le "$max" ]] || exit 2
[[ "$requested" -gt "$(date -u +%s)" ]] || exit 2
sed "s|^OnCalendar=.*|OnCalendar=$deadline|" \
  /etc/systemd/system/otel-demo-expire.timer > /tmp/otel-demo-expire.timer
install -m 0644 /tmp/otel-demo-expire.timer /etc/systemd/system/otel-demo-expire.timer
printf '%s\\n' "$deadline" > /etc/otel-demo-deadline
systemctl daemon-reload
systemctl restart otel-demo-expire.timer
EXTEND
chmod 0755 /usr/local/sbin/otel-demo-set-deadline
printf '%s' '{env64}' | base64 -d >/opt/otel-demo/demo.env
printf '%s' '{digests64}' | base64 -d >/opt/otel-demo/digests.lock
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io curl git
git -C /opt/otel-demo init
git -C /opt/otel-demo remote add origin {UPSTREAM}
git -C /opt/otel-demo fetch --depth=1 origin {commit}
git -C /opt/otel-demo checkout --detach FETCH_HEAD
[[ "$(git -C /opt/otel-demo rev-parse HEAD)" == "{commit}" ]]
cd /opt/otel-demo
printf '%s\\n' 'DEMO_VERSION={tag}' >>demo.env
systemctl enable --now docker
install -d -m 0755 /usr/local/lib/docker/cli-plugins
curl --fail --silent --show-error --location --retry 3 \\
  https://github.com/docker/compose/releases/download/v2.39.4/docker-compose-linux-x86_64 \\
  -o /tmp/docker-compose-linux-x86_64
curl --fail --silent --show-error --location --retry 3 \\
  https://github.com/docker/compose/releases/download/v2.39.4/docker-compose-linux-x86_64.sha256 \\
  -o /tmp/docker-compose-linux-x86_64.sha256
(cd /tmp && sha256sum -c docker-compose-linux-x86_64.sha256)
install -m 0755 /tmp/docker-compose-linux-x86_64 /usr/local/lib/docker/cli-plugins/docker-compose
compose=(docker compose -p otel-demo --env-file .env --env-file demo.env \
  -f compose.yaml -f compose.observability.yaml)
"${{compose[@]}}" config --quiet
while IFS= read -r image; do
  awk -F '\\t' -v image="$image" '$1 == image {{ found=1 }} END {{ exit !found }}' \
    digests.lock || exit 1
done < <("${{compose[@]}}" config --images)
while IFS=$'\\t' read -r image digest; do
  [[ -z "$image" ]] && continue
  repository="${{image%:*}}"
  docker pull "$repository@$digest"
  docker image tag "$repository@$digest" "$image"
done <digests.lock
"${{compose[@]}}" up -d --pull never --no-build
'''
    if len(script.encode()) > MAX_USER_DATA_BYTES:
        raise DemoError("bootstrap exceeds EC2's 16 KiB user-data limit")
    return script
