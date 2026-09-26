"""The installed package exposes the Rust authorization policy boundary."""

from importlib import import_module


def test_native_authorization_extension_imports_and_matches_an_exact_grant() -> None:
    native = import_module("sre_agent._core")

    assert native.API_VERSION == 1
    assert native.evaluate_authorization(
        "active",
        "human-subject",
        "invoke",
        "skill",
        "resource-id",
        ("skill", "resource-id", "active"),
        ("grant-skill", "human-subject", "invoke", "skill", "resource-id", "allow", "active"),
    ) == (True, "grant_matched", "grant-skill", None)
