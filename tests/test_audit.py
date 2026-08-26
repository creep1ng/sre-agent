import hmac  # noqa: I001

from sre_agent.gateway.audit import AuditProjector


def test_audit_references_follow_adr_005_domain_separation() -> None:
    key = b"test-audit-key-not-for-production"
    reference = AuditProjector(key).reference("principal", "incident-harness")
    expected = hmac.digest(key, b"sre-audit-v1\0principal\0incident-harness", "sha256").hex()
    assert reference.digest == expected and "incident-harness" not in repr(reference)
