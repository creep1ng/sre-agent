"""Native incident admission keeps ordered rejection and selected outcome."""

from importlib import import_module
from types import SimpleNamespace

import pytest


def _facts(**overrides: object) -> tuple[dict[str, str], object, object]:
    command = dict(
        actor="human",
        actor_reference=SimpleNamespace(reference_version="1.0.0", principal_id="operator_one"),
        approval=True,
        outcome=None,
    )
    command.update(overrides)
    transition = SimpleNamespace(
        source="mitigating",
        actors=frozenset({"human"}),
        requires_approval=True,
        outcomes=("approve",),
    )
    return {"state": "mitigating"}, SimpleNamespace(**command), transition


def test_native_admission_returns_typed_verdict_and_outcome() -> None:
    native = import_module("sre_agent._core")
    state, command, transition = _facts()
    assert native.admit_incident_transition(state, command, transition) == ("accepted", "approve")
    state["state"] = "investigating"
    assert native.admit_incident_transition(state, command, transition) == (
        "source_mismatch",
        None,
    )


def test_native_admission_does_not_read_facts_after_rejection() -> None:
    native = import_module("sre_agent._core")

    class Poison:
        @property
        def actor(self) -> str:
            raise AssertionError("actor read after source rejection")

    state, _, transition = _facts()
    state["state"] = "investigating"
    assert native.admit_incident_transition(state, Poison(), transition) == (
        "source_mismatch",
        None,
    )

    class PoisonReference:
        @property
        def principal_id(self) -> str:
            raise AssertionError("reference read after actor rejection")

    state, command, transition = _facts(actor="agent", actor_reference=PoisonReference())
    assert native.admit_incident_transition(state, command, transition) == (
        "actor_forbidden",
        None,
    )

    class PoisonPrincipal:
        reference_version = "2.0.0"

        @property
        def principal_id(self) -> str:
            raise AssertionError("principal read after version rejection")

    state, command, transition = _facts(actor_reference=PoisonPrincipal())
    assert native.admit_incident_transition(state, command, transition) == (
        "actor_reference_invalid",
        None,
    )

    class PoisonOutcome:
        actor = "human"
        actor_reference = SimpleNamespace(reference_version="1.0.0", principal_id="operator_one")
        approval = False

        @property
        def outcome(self) -> str:
            raise AssertionError("outcome read after approval rejection")

    assert native.admit_incident_transition(state, PoisonOutcome(), transition) == (
        "approval_required",
        None,
    )


def test_native_admission_skips_irrelevant_approval_property() -> None:
    native = import_module("sre_agent._core")

    class PoisonApproval:
        actor = "human"
        actor_reference = SimpleNamespace(reference_version="1.0.0", principal_id="operator_one")
        outcome = None

        @property
        def approval(self) -> bool:
            raise AssertionError("approval read when not needed")

    state, _, transition = _facts()
    transition.requires_approval = False
    transition.outcomes = ()
    assert native.admit_incident_transition(state, PoisonApproval(), transition) == (
        "accepted",
        None,
    )

    transition.requires_approval = True
    transition.actors = frozenset({"agent"})

    class AgentPoisonApproval:
        actor = "agent"
        actor_reference = None

        @property
        def approval(self) -> bool:
            raise AssertionError("approval read after nonhuman rejection")

    assert native.admit_incident_transition(state, AgentPoisonApproval(), transition) == (
        "approval_required",
        None,
    )


@pytest.mark.parametrize(
    ("override", "verdict"),
    [
        ({"actor": 7}, "actor_forbidden"),
        (
            {"actor_reference": SimpleNamespace(reference_version=7, principal_id="operator_one")},
            "actor_reference_invalid",
        ),
        ({"outcome": 7}, "outcome_required"),
    ],
)
def test_native_malformed_facts_return_typed_rejection(
    override: dict[str, object], verdict: str
) -> None:
    native = import_module("sre_agent._core")
    state, command, transition = _facts(**override)
    assert native.admit_incident_transition(state, command, transition) == (verdict, None)


def test_native_unconstrained_outcome_preserves_existing_value() -> None:
    native = import_module("sre_agent._core")
    state, command, transition = _facts(outcome=7)
    transition.outcomes = ()
    assert native.admit_incident_transition(state, command, transition) == ("accepted", 7)
