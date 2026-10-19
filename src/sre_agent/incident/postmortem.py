"""The durable postmortem artifact of an incident (HT-INC-ARTIFACTS, issue #335, first cut).

`start_postmortem` reserves the `pm_` identity in the incident state; the content
lives in its own versioned record, written and reviewed by humans through the
postmortem routes. `close_incident` trusts neither the prefix nor the state: it
reads this record and requires the current version to carry an approving review.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

MAX_TEXT = 4000
MAX_ITEMS = 50
CERTAINTY = frozenset({"confirmed", "probable", "hypothesis", "unknown"})
REVIEW_OUTCOMES = frozenset({"approved", "changes_requested"})
EVENT_ID_PATTERN = r"^evt_[a-z0-9_-]{1,60}$"
# The #43 CA2 minimum. Every section is required; what is not known is declared
# in `unknowns` or graded `unknown`, never left out.
SECTIONS = frozenset(
    {
        "summary",
        "impact",
        "timeline",
        "cause",
        "strategy",
        "actions_taken",
        "verification",
        "pending",
        "unknowns",
    }
)


class InvalidPostmortemError(ValueError):
    """The content does not satisfy the minimum postmortem contract."""


@dataclass(frozen=True, slots=True)
class PostmortemReview:
    version: int
    outcome: str
    reviewer_id: str
    comment: str | None
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class PostmortemRecord:
    postmortem_id: str
    incident_id: str
    version: int
    content: Mapping[str, Any]
    run_ids: tuple[str, ...]
    updated_by: str
    created_at: datetime
    updated_at: datetime
    review: PostmortemReview | None

    @property
    def approved(self) -> bool:
        """Only a review of the current version counts; an edit voids older ones."""
        return (
            self.review is not None
            and self.review.version == self.version
            and self.review.outcome == "approved"
        )


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise InvalidPostmortemError(f"{field} must be nonblank text of at most {MAX_TEXT}")
    return value


def _items(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list) or len(value) > MAX_ITEMS:
        raise InvalidPostmortemError(f"{field} must be a list of at most {MAX_ITEMS}")
    return value


def _cited(value: Any, field: str) -> str:
    if not isinstance(value, dict) or set(value) != {"event_id", "description"}:
        raise InvalidPostmortemError(f"{field} entries require exactly event_id and description")
    _text(value["description"], field)
    event_id = value["event_id"]
    if not isinstance(event_id, str) or re.fullmatch(EVENT_ID_PATTERN, event_id) is None:
        raise InvalidPostmortemError(f"{field} entries must cite an event id")
    return event_id


def validate_content(content: Any) -> frozenset[str]:
    """Check the minimum sections and return every event id the content cites.

    The caller still has to prove those events exist for this incident: a well
    formed citation is not evidence.
    """

    if not isinstance(content, dict) or set(content) != SECTIONS:
        raise InvalidPostmortemError(f"content requires exactly {sorted(SECTIONS)}")
    for field in ("summary", "impact", "strategy", "verification"):
        _text(content[field], field)
    cause = content["cause"]
    if (
        not isinstance(cause, dict)
        or set(cause) != {"statement", "certainty"}
        or cause["certainty"] not in CERTAINTY
    ):
        raise InvalidPostmortemError(f"cause requires a statement and a {sorted(CERTAINTY)} grade")
    _text(cause["statement"], "cause.statement")
    for field in ("pending", "unknowns"):
        for item in _items(content[field], field):
            _text(item, field)
    timeline = _items(content["timeline"], "timeline")
    if not timeline:
        raise InvalidPostmortemError("timeline requires at least one cited event")
    cited = {_cited(entry, "timeline") for entry in timeline}
    # An action is listed as performed only with the event that confirms it (#43 CA3).
    actions = _items(content["actions_taken"], "actions_taken")
    cited |= {_cited(entry, "actions_taken") for entry in actions}
    return frozenset(cited)
