"""Per-call OpenAI usage + cost ledger.

One row per LLM call (chat completion OR embedding). Written by
app.services.llm_usage.log_llm_usage. Never touched during the
call's critical path — a DB hiccup on this table must not break
the pipeline, so the logger swallows its own errors.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LLMUsageLog(Base):
    __tablename__ = "llm_usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # The OpenAI model name returned by the API (e.g. gpt-4o-mini-2024-07-18).
    # The pricing resolver strips dated snapshots to the base key.
    model: Mapped[str] = mapped_column(String(80), index=True)
    # Short tag identifying WHY this call ran: bias_scoring,
    # story_analysis.main.premium, telegram.pass2.baseline, etc.
    purpose: Mapped[str] = mapped_column(String(80), index=True)

    # Token counts from response.usage. cached_input_tokens is a subset
    # of input_tokens per OpenAI's accounting.
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # Per-component costs so the dashboard can explain a total in one glance.
    input_cost: Mapped[float] = mapped_column(Float, default=0.0)
    cached_cost: Mapped[float] = mapped_column(Float, default=0.0)
    output_cost: Mapped[float] = mapped_column(Float, default=0.0)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    # Optional attribution so the dashboard can show "the 3 most expensive
    # stories this week". Both nullable — embeddings often have neither.
    story_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
    )
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
    )

    # Flag calls where the pricing table didn't know this model (total_cost
    # ends up 0 even though tokens were spent). Dashboard surfaces this
    # so we remember to add the model's price.
    priced: Mapped[bool] = mapped_column(default=True)

    # Free-form extra context — channel slug for telegram calls, model
    # tier label, prompt variant id, etc. Kept JSONB so we can filter
    # without adding more columns as the taxonomy grows.
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<LLMUsageLog {self.purpose}/{self.model} ${self.total_cost:.5f}>"
