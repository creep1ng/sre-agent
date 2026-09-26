"""Characterize native OpenRouter completed text selection."""

import pytest

from sre_agent import _core
from sre_agent.gateway.openrouter import _completed_output_text
from sre_agent.gateway.providers import ProviderFailure


def _message(
    *parts: object, role: str = "assistant", status: str = "completed"
) -> dict[str, object]:
    return {"type": "message", "role": role, "status": status, "content": list(parts)}


def _text(value: object) -> dict[str, object]:
    return {"type": "output_text", "text": value}


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"status": "completed", "output": [_message(_text(""))]}, ""),
        ({"status": "completed", "output": [_message(_text(""), _text(""))]}, "\n"),
        (
            {
                "status": "completed",
                "output": [
                    _message(_text("ignored"), role="user"),
                    _message(_text("ignored"), status="in_progress"),
                    {"type": "reasoning", "content": [_text("ignored")]},
                    _message(_text("first"), 9, _text(3), _text("second")),
                    _message(_text("third")),
                ],
            },
            "first\nsecond\nthird",
        ),
        ({"status": "completed", "output": [_message(_text("\ud800"))]}, "\ud800"),
    ],
)
def test_native_and_adapter_preserve_selected_python_text(
    body: dict[str, object], expected: str
) -> None:
    assert _core.completed_openrouter_output_text(body) == expected
    assert _completed_output_text(body) == expected


@pytest.mark.parametrize(
    "body",
    [
        {"status": "in_progress", "output": [_message(_text("partial"))]},
        {"status": "completed", "output": {}},
        {"status": "completed", "output": []},
        {"status": "completed", "output": [_message(_text(3))]},
        {"status": "completed", "output": [_message(_text("skip"), role="user")]},
    ],
)
def test_native_and_adapter_reject_missing_qualifying_text(body: dict[str, object]) -> None:
    assert _core.completed_openrouter_output_text(body) is None
    with pytest.raises(ProviderFailure) as captured:
        _completed_output_text(body)
    assert captured.value.kind == "invalid_response"
