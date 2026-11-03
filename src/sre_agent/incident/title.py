"""The incident's short title, the one field of model output the safe projections let through.

Maintainer decision of 2026-11-03 (#870): the investigator names the incident in a few words
(«Fallan los cobros en checkout») so a person recognises it in the inbox, the incident page and
Telegram. The title is untrusted model output, so it is checked wherever it is written or read:
plain text on a single line, control and invisible formatting characters stripped, at most
MAX_TITLE characters. Anything else is no title, and every reader falls back to the alert's own
words. See agent/api/projection-policy.v1.yaml (model_output_exception).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

MAX_TITLE = 60
_LINE_BREAK = re.compile(r"[\n\r\v\f\x1c-\x1e\x85  ]")
# C0 and C1 controls, zero-width characters and bidirectional overrides.
_HIDDEN = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮⁠-⁤⁦-⁩﻿]")


def clean_title(value: Any) -> str | None:
    """The title as shown, or None when it is not one: not text, several lines, empty or long."""
    if not isinstance(value, str) or _LINE_BREAK.search(value.strip()):
        return None
    title = " ".join(_HIDDEN.sub("", value).split())
    return title if 0 < len(title) <= MAX_TITLE else None


def title_of(state: Any) -> str | None:
    """The latest hypothesis's title: a later hypothesis renames the incident, or unnames it."""
    hypotheses = state.get("hypotheses") if isinstance(state, Mapping) else None
    latest = hypotheses[-1] if isinstance(hypotheses, list) and hypotheses else None
    return clean_title(latest.get("title")) if isinstance(latest, Mapping) else None
