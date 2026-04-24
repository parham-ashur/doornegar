"""Shared event-log writer for decision queue + audit trail.

All HITL actions (freeze / split / merge / rename) and significant
pipeline decisions (cluster_new / match_accept / match_reject / review
tier promotions) emit one row here so the UI can render a single
timeline per story or per actor.

Non-fatal: if the insert fails we log and swallow the error — event
logging must never block the underlying action.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


_TRUNCATE = 2000  # cap text column size per event


def _clip(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value)
    if len(s) > _TRUNCATE:
        return s[: _TRUNCATE] + "…"
    return s


async def log_event(
    db: AsyncSession,
    *,
    event_type: str,
    actor: str = "pipeline",
    story_id: uuid.UUID | None = None,
    article_id: uuid.UUID | None = None,
    field: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
    confidence: float | None = None,
    signals: dict | None = None,
    commit: bool = False,
) -> None:
    """Insert a story_events row. By default does NOT commit — the caller's
    transaction carries it. Pass commit=True for fire-and-forget calls
    from scripts.

    event_type conventions:
      - Pipeline decisions: `cluster_new`, `match_accept`, `match_reject`,
        `merge`, `tier_promoted`, `noise_filtered`
      - HITL actions: `freeze`, `unfreeze`, `split`, `arc_scaffold`,
        `arc_assign`
      - Field edits: `field_change` (use `field`/old_value/new_value)

    actor conventions: `pipeline`, `niloofar`, `admin`, `bot`
    """
    try:
        await db.execute(
            text(
                """
                INSERT INTO story_events
                  (story_id, article_id, event_type, actor, field,
                   old_value, new_value, confidence, signals)
                VALUES
                  (:story_id, :article_id, :event_type, :actor, :field,
                   :old_value, :new_value, :confidence,
                   CAST(:signals AS jsonb))
                """
            ),
            {
                "story_id": story_id,
                "article_id": article_id,
                "event_type": event_type,
                "actor": actor,
                "field": field,
                "old_value": _clip(old_value),
                "new_value": _clip(new_value),
                "confidence": confidence,
                "signals": json.dumps(signals, ensure_ascii=False) if signals else None,
            },
        )
        if commit:
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        # Event logging is advisory — never block the caller.
        logger.warning("story_events insert failed (non-fatal): %s", exc)
