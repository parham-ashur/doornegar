"""summary_anchor: editorial anchor instead of frozen lock

Revision ID: t5o6p7q8r9s0
Revises: s4n5o6p7q8r9
Create Date: 2026-04-26 15:00:00.000000

Why:
- The old `is_edited=true` semantics froze a story's analysis forever.
  New articles still attached to the cluster, but the bias panel and
  side summaries stopped updating. Result: a 12-article story
  displaying narrative written when only 6 were in.
- New semantics: admin edits become a *reference* the LLM is asked to
  preserve while it integrates new articles. summary_anchor stores
  the canonical fields. step_summarize injects them into the prompt
  with a "preserve tone, preserve key vocabulary, only add new facts"
  instruction.
- One-shot data migration copies existing is_edited stories' current
  state_summary_fa / diaspora_summary_fa / bias_explanation_fa into
  summary_anchor, so admin polish carries over the moment the next
  cron tick re-evaluates them.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "t5o6p7q8r9s0"
down_revision: Union[str, None] = "s4n5o6p7q8r9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE stories "
        "ADD COLUMN IF NOT EXISTS summary_anchor JSONB"
    )
    # Backfill: for every is_edited story, copy the relevant fields
    # from summary_en (where the analysis blob lives) into a fresh
    # summary_anchor JSONB. Stories that don't have those fields get
    # NULL anchor — they'll behave as un-anchored on the next cron.
    op.execute(
        """
        UPDATE stories
        SET summary_anchor = jsonb_build_object(
            'state_summary_fa', summary_en::jsonb -> 'state_summary_fa',
            'diaspora_summary_fa', summary_en::jsonb -> 'diaspora_summary_fa',
            'bias_explanation_fa', summary_en::jsonb -> 'bias_explanation_fa',
            'summary_fa', to_jsonb(summary_fa),
            'title_fa', to_jsonb(title_fa),
            'anchored_at', to_jsonb(NOW())
        )
        WHERE is_edited = true
          AND summary_en IS NOT NULL
          AND summary_anchor IS NULL
          AND (summary_en::jsonb ? 'state_summary_fa'
               OR summary_en::jsonb ? 'diaspora_summary_fa'
               OR summary_en::jsonb ? 'bias_explanation_fa')
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stories DROP COLUMN IF EXISTS summary_anchor")
