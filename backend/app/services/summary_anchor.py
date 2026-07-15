"""Shared helper for the summary_anchor editorial-preservation pattern.

2026-07-15: this exact "write is_edited=True and never touch summary_anchor"
bug was independently found in THREE separate manual-edit code paths
(admin.py's PATCH /admin/stories/{id} -- already fixed, its own "#6" comment
-- scripts/journalist_audit.py's apply_fix(), and hitl.py's
PATCH /hitl/stories/{story_id}/narrative). Each permanently excludes the
story from step_summarize / step_summarize_newly_visible's eligibility gate
(`is_edited=False OR summary_anchor IS NOT NULL`), so any manually-edited
story could only ever be refreshed again by another manual edit -- the
opposite of the self-running goal. A shared helper exists so a fourth
occurrence of this class of bug requires actively NOT calling this function,
rather than reinventing (and potentially forgetting) the anchor write.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def apply_editorial_anchor(story: Any, **fields: str | None) -> None:
    """Merge non-None fields into story.summary_anchor and stamp anchored_at.

    Does NOT touch story.is_edited -- callers decide that separately, since
    the right value differs by call site (admin.py's PATCH sets it False so
    nightly maintenance keeps refreshing the story; journalist_audit.py
    deliberately keeps it True to preserve the oversized-active freeze
    exemption + auto-merge protection that growing pinned war stories need).
    Either way, writing the anchor alone is sufficient to unlock refresh
    eligibility via the OR in the gate.
    """
    anchor = dict(story.summary_anchor or {})
    for key, value in fields.items():
        if value is not None:
            anchor[key] = value
    anchor["anchored_at"] = datetime.now(timezone.utc).isoformat() + "Z"
    story.summary_anchor = anchor
