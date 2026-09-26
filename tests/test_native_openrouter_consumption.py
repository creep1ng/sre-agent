"""Characterize the usage projection boundary without changing provider evidence."""

from sre_agent import _core


def test_native_usage_projection_is_single_authority() -> None:
    complete = _core.project_openrouter_consumption(
        "mapping",
        True,
        ("11", False, True),
        ("7", False, True),
        ("18", False, True),
        ("0.0012300", False, True),
        True,
    )
    assert complete == ("complete", "11", "7", "18", "0.0012300", True)
    assert _core.project_openrouter_consumption(
        "mapping",
        True,
        ("11", False, True),
        ("7", False, True),
        ("17", False, True),
        ("0.0012300", False, True),
        True,
    ) == ("partial", "11", "7", None, "0.0012300", True)
    assert _core.project_openrouter_consumption(
        "mapping",
        True,
        ("11", False, True),
        ("7", False, True),
        ("18", False, True),
        ("0.0012300", False, True),
        False,
    ) == ("partial", "11", "7", "18", None, False)


def test_native_empty_usage_projects_null_fields() -> None:
    missing = (None, False, False)
    for state, nonempty, availability in [
        ("missing", False, "absent"),
        ("invalid", False, "unavailable"),
        ("mapping", False, "absent"),
        ("mapping", True, "unavailable"),
    ]:
        assert _core.project_openrouter_consumption(
            state, nonempty, missing, missing, missing, missing, False
        ) == (availability, None, None, None, None, False)

    assert _core.project_openrouter_consumption(
        "missing", False, missing, missing, missing, missing, False, True
    ) == ("unavailable", None, None, None, None, False)
