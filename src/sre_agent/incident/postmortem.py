"""The durable postmortem artifact of an incident (HT-INC-ARTIFACTS, issue #335, first cut).

`start_postmortem` reserves the `pm_` identity in the incident state; the content
lives in its own versioned record, written and reviewed by humans through the
postmortem routes. `close_incident` trusts neither the prefix nor the state: it
reads this record and requires the current version to carry an approving review.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


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
