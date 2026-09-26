"""ADR-005 HMAC vectors at the native audit-reference boundary."""

import builtins
import hmac

import pytest
from pydantic import ValidationError

from sre_agent import _core
from sre_agent.gateway.audit import AuditProjector


@pytest.mark.parametrize(
    ("domain", "value"),
    [
        ("principal", "incident-harness"),
        ("principal", "é🦉\x00value"),
        ("princípal", "é🦉\x00value"),
        ("resource", "é🦉\x00value"),
    ],
)
def test_native_digest_matches_adr_005_canonical_bytes(domain: str, value: str) -> None:
    key = b"test-audit-key-not-for-production"
    data = f"sre-audit-v1\0{domain}\0{value}".encode()
    expected = hmac.digest(key, data, "sha256").hex()

    assert _core.audit_reference_digest(key, domain, value) == expected
    assert AuditProjector(key).reference(domain, value).digest == expected


def test_audit_reference_key_version_is_envelope_only() -> None:
    key = b"test-audit-key-not-for-production"
    first = AuditProjector(key, key_version=1).reference("principal", "same-value")
    second = AuditProjector(key, key_version=2).reference("principal", "same-value")

    assert first.algorithm == second.algorithm == "hmac-sha-256"
    assert first.key_version == 1
    assert second.key_version == 2
    assert first.digest == second.digest
    with pytest.raises(ValidationError):
        AuditProjector(key, key_version=0).reference("principal", "same-value")


def test_audit_reference_uses_native_crypto_not_python_hmac_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_python_hmac(*args: object, **kwargs: object) -> None:
        raise AssertionError("Python hmac.new must not run in production")

    expected = AuditProjector(b"key").reference("principal", "same-value").digest
    monkeypatch.setattr(hmac, "new", reject_python_hmac)

    assert AuditProjector(b"key").reference("principal", "same-value").digest == expected


def test_native_reference_preserves_f_string_formatting_and_key_error() -> None:
    class Formatted:
        def __format__(self, spec: str) -> str:
            assert spec == ""
            return "formatted-value"

    key = b"key"
    expected = hmac.digest(key, b"sre-audit-v1\0principal\0formatted-value", "sha256").hex()

    assert _core.audit_reference_digest(key, "principal", Formatted()) == expected
    with pytest.raises(TypeError):
        AuditProjector("not-bytes").reference("principal", "value")  # type: ignore[arg-type]


def test_native_reference_accepts_bytearray_but_rejects_other_buffer_keys() -> None:
    expected = AuditProjector(b"key").reference("principal", "value").digest

    assert AuditProjector(bytearray(b"key")).reference("principal", "value").digest == expected
    with pytest.raises(TypeError, match="key: expected bytes or bytearray"):
        AuditProjector(memoryview(b"key")).reference("principal", "value")


def test_native_reference_ignores_replaced_builtin_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = b"key"
    expected = hmac.digest(key, b"sre-audit-v1\0principal\0value", "sha256").hex()

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "format", lambda *_args: "corrupt")
        native = _core.audit_reference_digest(key, "principal", "value")
        projected = AuditProjector(key).reference("principal", "value").digest

    assert native == projected == expected


def test_native_reference_formats_both_fields_before_utf8_encoding() -> None:
    class FailsOnFormat:
        def __format__(self, _spec: str) -> str:
            raise RuntimeError("value format sentinel")

    with pytest.raises(RuntimeError, match="value format sentinel"):
        _core.audit_reference_digest(b"key", "\ud800", FailsOnFormat())
    with pytest.raises(RuntimeError, match="value format sentinel"):
        AuditProjector(b"key").reference("\ud800", FailsOnFormat())


@pytest.mark.parametrize(
    ("domain", "value"),
    [
        ("\ud800", "value"),
        ("ab\ud800", "value"),
        ("domain", "\ud800"),
        ("domain", "x\ud800"),
    ],
)
def test_native_reference_matches_whole_string_unicode_encode_error(
    domain: str, value: str
) -> None:
    # HEAD encoded the fully formatted string, so error offsets and object
    # refer to the canonical input rather than an individual field.
    canonical = f"sre-audit-v1\0{domain}\0{value}"
    with pytest.raises(UnicodeEncodeError) as expected:
        canonical.encode()

    for reference in (
        lambda: _core.audit_reference_digest(b"key", domain, value),
        lambda: AuditProjector(b"key").reference(domain, value),
    ):
        with pytest.raises(UnicodeEncodeError) as actual:
            reference()
        assert (
            actual.value.encoding,
            actual.value.object,
            actual.value.start,
            actual.value.end,
            actual.value.reason,
        ) == (
            expected.value.encoding,
            expected.value.object,
            expected.value.start,
            expected.value.end,
            expected.value.reason,
        )
