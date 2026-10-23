"""The gateway's signature on every operation request (#743).

The executor is the hands, not the policy: it knows no principal and no
grant. It only checks that the exact request in front of it was produced by
the one caller holding the key. ``v1`` is HMAC-SHA256 over the method, the
path, the ``Idempotency-Key``, the SHA-256 of the body and a Unix timestamp.
The window bounds a captured request; inside it, the idempotency journal
makes a re-sent request replay its stored result instead of running again.
"""

from __future__ import annotations

import hashlib
import hmac
from time import time

TIMESTAMP_HEADER = "x-executor-timestamp"
SIGNATURE_HEADER = "x-executor-signature"
MIN_KEY_LENGTH = 32


def usable_key(value: str | None) -> bytes | None:
    """The configured key, or None when it is absent, a placeholder or too short."""
    if value is None or len(value) < MIN_KEY_LENGTH or "<" in value or ">" in value:
        return None
    return value.encode()


def sign(
    key: bytes, method: str, path: str, idempotency_key: str, body: bytes, timestamp: str
) -> str:
    """``v1=<hex>`` over these exact request parts: what the gateway sends, what is expected."""
    digest = hashlib.sha256(body).hexdigest()
    message = "\n".join((method.upper(), path, idempotency_key, digest, timestamp)).encode()
    return "v1=" + hmac.new(key, message, hashlib.sha256).hexdigest()


def verify(
    key: bytes,
    window_seconds: float,
    method: str,
    path: str,
    idempotency_key: str,
    body: bytes,
    timestamp: str,
    signature: str,
) -> str | None:
    """The public error code that rejects the request, or None when the signature holds."""
    if not timestamp or not signature:
        return "signature_missing"
    if not (timestamp.isascii() and timestamp.isdigit()):
        return "signature_invalid"
    if abs(time() - int(timestamp)) > window_seconds:
        return "signature_expired"
    expected = sign(key, method, path, idempotency_key, body, timestamp)
    if not hmac.compare_digest(expected, signature):
        return "signature_invalid"
    return None
