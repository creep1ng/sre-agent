"""Holds flagd's EventStream open (Connect protocol, as the store's providers stream it) for
DURATION seconds and prints each event with its time; says whether the stream outlived it."""

import http.client
import json
import os
import struct
import sys
import threading
import time

duration = float(sys.argv[1])
connection = http.client.HTTPConnection(os.environ.get("FLAGD_HOST", "flagd"), 8013)
body = b"{}"
connection.request(
    "POST",
    "/flagd.evaluation.v1.Service/EventStream",
    struct.pack(">BI", 0, len(body)) + body,
    {"Content-Type": "application/connect+json", "Connect-Protocol-Version": "1"},
)
response = connection.getresponse()
started = time.monotonic()
print(f"{0:6.1f}s status {response.status}", flush=True)
done = threading.Event()


def read():
    try:
        while True:
            head = response.read(5)
            if len(head) < 5:
                print(f"{time.monotonic() - started:6.1f}s stream ended", flush=True)
                break
            _, size = struct.unpack(">BI", head)
            event = json.loads(response.read(size) or b"{}")
            print(f"{time.monotonic() - started:6.1f}s {event.get('type') or event}", flush=True)
    except (OSError, http.client.HTTPException) as error:
        print(
            f"{time.monotonic() - started:6.1f}s stream broken: {type(error).__name__}", flush=True
        )
    done.set()


threading.Thread(target=read, daemon=True).start()
if not done.wait(duration):
    print(f"{duration:6.1f}s window over; the stream is still open", flush=True)
