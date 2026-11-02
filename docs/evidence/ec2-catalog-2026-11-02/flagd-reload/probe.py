"""Writes the flag file as the guest does (an atomic replace) and in place (as upstream flagd-ui
does), never restarting flagd, and measures when flagd serves each new variant."""

import json
import os
import time
import urllib.request

FLAGS = "/probe/flagd/demo.flagd.json"
OFREP = "http://" + os.environ.get("FLAGD_HOST", "flagd") + ":8016/ofrep/v1/evaluate/flags/"


def served(flag):
    request = urllib.request.Request(
        OFREP + flag, b'{"context":{}}', {"Content-Type": "application/json"}
    )
    return json.load(urllib.request.urlopen(request))["variant"]


def write(flag, variant, how):
    data = json.load(open(FLAGS))
    data["flags"][flag]["defaultVariant"] = variant
    text = json.dumps(data, indent=2) + "\n"
    if how == "replace":  # mcp_guest.py replace_flags: a temporary file, then os.replace
        with open(FLAGS[:-5] + ".tmp", "w") as stream:
            stream.write(text)
        os.replace(FLAGS[:-5] + ".tmp", FLAGS)
    else:
        with open(FLAGS, "r+") as stream:
            stream.seek(0)
            stream.write(text)
            stream.truncate()


def until(flag, variant, timeout=15):
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if served(flag) == variant:
            return round(time.monotonic() - started, 2)
        time.sleep(0.1)
    return None


for flag, variant, how in (
    ("paymentUnreachable", "on", "replace"),
    ("paymentUnreachable", "off", "replace"),
    ("paymentFailure", "100%", "replace"),
    ("paymentFailure", "off", "in place"),
    ("paymentUnreachable", "on", "in place"),
    ("paymentUnreachable", "off", "replace"),
):
    write(flag, variant, how)
    print(f"{how:8} {flag}={variant}: flagd serves it after {until(flag, variant)} s", flush=True)
