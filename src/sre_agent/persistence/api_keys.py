"""API-key material primitives owned by the persistence boundary."""

import hashlib
import hmac
import re
import secrets

# The contract allows 24..128 suffix characters: 28..132 characters including ``sre_``.
KEY_PATTERN = re.compile(r"sre_[A-Za-z0-9_-]{24,128}")
# ``sre_`` plus 12 URL-safe random characters retains 72 random prefix bits.
PREFIX_LENGTH = 16
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 64


def generate_api_key() -> str:
    """Create key material suitable for a one-time issuance response."""
    return f"sre_{secrets.token_urlsafe(32)}"


def is_api_key(value: str) -> bool:
    return KEY_PATTERN.fullmatch(value) is not None


def api_key_prefix(value: str, *, length: int = PREFIX_LENGTH) -> str:
    return value[:length]


def candidate_prefixes(value: str) -> tuple[str, ...]:
    """Return every prefix length permitted by CredentialReference."""
    return tuple(value[:length] for length in range(4, PREFIX_LENGTH + 1))


def hash_api_key(value: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        value.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_api_key(value: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if (algorithm, int(n), int(r), int(p)) != (
            "scrypt",
            _SCRYPT_N,
            _SCRYPT_R,
            _SCRYPT_P,
        ):
            return False
        actual = hashlib.scrypt(
            value.encode(),
            salt=bytes.fromhex(salt),
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=_DKLEN,
        )
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False
