"""Send one change event to Midnight's POST /v1/changes (issue #770). Standard library only.

The record-change action sets these variables; any runner (or `docker run`) can too:
MIDNIGHT_URL, MIDNIGHT_API_KEY, CHANGE_SERVICE and CHANGE_EXTERNAL_ID are required;
CHANGE_SOURCE, CHANGE_KIND, CHANGE_STATUS, CHANGE_VERSION, CHANGE_COMMIT, CHANGE_REF,
CHANGE_AUTHOR, CHANGE_URL and FAIL_ON_ERROR are optional. The event is idempotent by
(source, external_id, service), so a transport error or a 5xx is simply sent again.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

FIELDS = {
    "source": "CHANGE_SOURCE",
    "external_id": "CHANGE_EXTERNAL_ID",
    "service": "CHANGE_SERVICE",
    "kind": "CHANGE_KIND",
    "status": "CHANGE_STATUS",
    "version": "CHANGE_VERSION",
    "commit_sha": "CHANGE_COMMIT",
    "ref": "CHANGE_REF",
    "author": "CHANGE_AUTHOR",
    "url": "CHANGE_URL",
}
DEFAULTS = {"source": "github-actions", "kind": "deploy", "status": "succeeded"}


def send() -> str:
    env = os.environ
    body = {name: env.get(var) or DEFAULTS.get(name) for name, var in FIELDS.items()}
    request = urllib.request.Request(
        env["MIDNIGHT_URL"].rstrip("/") + "/v1/changes",
        data=json.dumps({k: v for k, v in body.items() if v}).encode(),
        headers={
            "Authorization": f"Bearer {env['MIDNIGHT_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=15) as reply:
                answer = json.load(reply)
            state = "recorded" if answer["created"] else "already recorded"
            return f"{state} {answer['change']['change_id']} ({reply.status})"
        except urllib.error.HTTPError as error:
            if error.code < 500 or attempt == 2:
                detail = error.read()[:500]
                raise RuntimeError(f"Midnight answered {error.code}: {detail!r}") from None
        except OSError as error:  # unreachable, refused, reset or timed out: send it again
            if attempt == 2:
                reason = getattr(error, "reason", error)
                raise RuntimeError(f"Midnight is unreachable: {reason}") from None
        time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


if __name__ == "__main__":
    try:
        print(f"Change event {send()}.")
    except Exception as error:
        # The deploy already happened: by default a missing record warns instead of failing it.
        # Whatever went wrong (no URL, a timeout, a reply that is not JSON) takes this path; the
        # messages name the URL and the answer, never the key, which only travels in a header.
        message = f"change event not recorded: {type(error).__name__}: {error}"
        if os.environ.get("FAIL_ON_ERROR", "false") == "true":
            sys.exit(f"::error::{message}")
        print(f"::warning::{message}")
