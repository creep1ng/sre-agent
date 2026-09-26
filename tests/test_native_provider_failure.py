"""The native core owns the provider-failure taxonomy mapping."""

from importlib import import_module

import pytest


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("timeout", (504, "upstream_failed", "upstream_timeout")),
        ("unavailable", (503, "upstream_unavailable", "upstream_unavailable")),
        ("evidence_invalid", (502, "upstream_invalid", "provider_evidence_invalid")),
        ("invalid_response", (502, "upstream_invalid", "upstream_invalid_response")),
        ("future_failure", (502, "upstream_invalid", "upstream_invalid_response")),
    ],
)
def test_native_provider_failure_mapping_preserves_existing_taxonomy(
    kind: str, expected: tuple[int, str, str]
) -> None:
    native = import_module("sre_agent._core")

    assert native.map_provider_failure(kind) == expected


@pytest.mark.parametrize("kind", [7, None, b"timeout"])
def test_native_provider_failure_mapping_treats_non_strings_as_unknown(kind: object) -> None:
    native = import_module("sre_agent._core")

    assert native.map_provider_failure(kind) == (
        502,
        "upstream_invalid",
        "upstream_invalid_response",
    )
