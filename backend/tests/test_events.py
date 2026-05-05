"""Tests for `app/services/events.py` — round 7 of survival roadmap #9.

`log_event` is on the audit trail's hot path — every HITL action and
significant pipeline decision goes through it. Two invariants are
load-bearing:

1. The INSERT is SAVEPOINT-wrapped so a failed event never poisons the
   caller's outer transaction. Without this, a single bad insert mid-
   loop in `step_cluster` aborts the whole transaction and surfaces
   later as `greenlet_spawn has not been called`. (See the docstring
   in events.py:63-72.)

2. Failures are logged + swallowed, never raised. Event logging is
   advisory — blocking the underlying action would be worse than
   losing the audit row.

Run: `cd backend && pytest tests/test_events.py -v`
"""

from pathlib import Path
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.events import _clip, log_event


# ═════════════════════════════════════════════════════════════════════
# 1. _clip — truncation guard for text columns
# ═════════════════════════════════════════════════════════════════════

class TestClip:
    """story_events.old_value / new_value are TEXT columns. Without a
    cap, a 100KB diff (rare but possible — full bias_explanation_fa
    edit) bloats the row."""

    def test_none_passes_through(self):
        assert _clip(None) is None

    def test_empty_string(self):
        assert _clip("") == ""

    def test_short_string_unchanged(self):
        assert _clip("hello") == "hello"

    def test_long_string_truncated_with_ellipsis(self):
        long = "x" * 5000
        out = _clip(long)
        # 2000-char cap + ellipsis (1 char) → 2001
        assert len(out) == 2001
        assert out.endswith("…")

    def test_exactly_at_boundary_not_truncated(self):
        # 2000 chars exactly → no truncation, no ellipsis.
        s = "x" * 2000
        assert _clip(s) == s

    def test_one_over_boundary_truncated(self):
        s = "x" * 2001
        out = _clip(s)
        assert out.endswith("…")
        assert len(out) == 2001  # 2000 chars + 1 ellipsis

    def test_non_string_coerced(self):
        # Numbers / dicts / UUIDs may show up in old_value/new_value.
        assert _clip(42) == "42"
        assert _clip({"a": 1}) == str({"a": 1})


# ═════════════════════════════════════════════════════════════════════
# 2. log_event swallows errors — caller transaction must survive
# ═════════════════════════════════════════════════════════════════════

class TestLogEventErrorSwallowing:
    """If `log_event` raises, the caller's outer transaction breaks.
    Real incident pattern: cluster_step calls log_event 100s of times
    in a loop; one mid-loop failure used to brick the rest of the
    loop and surface later as `greenlet_spawn has not been called`
    on the next autoflush. The fix wraps the insert in begin_nested
    + a try/except that logs and continues."""

    @pytest.mark.asyncio
    async def test_db_error_does_not_propagate(self):
        # `db.begin_nested()` is a sync call that returns an async
        # context manager — model that with MagicMock, not AsyncMock.
        db = MagicMock()
        db.begin_nested = MagicMock(side_effect=RuntimeError("connection dropped"))

        # Must NOT raise.
        await log_event(
            db,
            event_type="cluster_new",
            actor="pipeline",
        )

    @pytest.mark.asyncio
    async def test_execute_error_inside_savepoint_swallowed(self):
        """Failure inside the SAVEPOINT (FK violation, bad column, etc.)
        must be caught — the SAVEPOINT rolls back, the outer tx is
        unaffected, and log_event returns normally."""
        @asynccontextmanager
        async def fake_savepoint():
            yield

        db = MagicMock()
        db.begin_nested = MagicMock(return_value=fake_savepoint())
        # The INSERT raises.
        db.execute = AsyncMock(side_effect=RuntimeError("FK violation"))

        await log_event(
            db,
            event_type="match_accept",
            actor="pipeline",
        )
        # No assertion needed — reaching here means no propagation.


# ═════════════════════════════════════════════════════════════════════
# 3. Source-inspection: SAVEPOINT + parameterized SQL invariants
# ═════════════════════════════════════════════════════════════════════

class TestLogEventSourceInvariants:
    """Two structural rules that the unit-tests above can't easily
    verify: the use of begin_nested (SAVEPOINT) and parameterized
    SQL bindings. Source inspection catches refactors that would
    silently regress these."""

    def test_uses_begin_nested_savepoint(self):
        src = (
            Path(__file__).parent.parent / "app" / "services" / "events.py"
        ).read_text()
        assert "db.begin_nested()" in src, (
            "log_event must wrap its INSERT in db.begin_nested() so "
            "a failed insert can't poison the caller's outer "
            "transaction. Removing the SAVEPOINT regresses the fix "
            "for the 2026-04-29 greenlet_spawn incident."
        )

    def test_uses_parameterized_sql_bindings(self):
        """The INSERT must use bound parameters, never f-string
        interpolation. story_events accepts user-supplied strings
        (titles, error messages); a stray f-string opens SQL injection."""
        src = (
            Path(__file__).parent.parent / "app" / "services" / "events.py"
        ).read_text()
        # The INSERT block should use :param style bindings.
        assert ":story_id" in src
        assert ":event_type" in src
        # Never use f-string substitution into the SQL body.
        assert "INSERT INTO story_events" in src
        # Pull out the INSERT region and check for bare f-strings.
        idx = src.find("INSERT INTO story_events")
        end = src.find('"""', idx)
        if end == -1:
            end = src.find("'''", idx)
        insert_block = src[idx:end] if end > 0 else ""
        # The SQL body itself must contain only :placeholders (no
        # backtick-style f-string formatting markers).
        assert "{" not in insert_block, (
            "INSERT body uses { — looks like f-string interpolation. "
            "All values must go through bound parameters."
        )

    def test_swallow_pattern_in_place(self):
        """The try/except wrapping the SAVEPOINT must catch a broad
        Exception and log+continue. Tightening the exception type
        (e.g. catching only sqlalchemy errors) would re-expose the
        connection-drop bug."""
        src = (
            Path(__file__).parent.parent / "app" / "services" / "events.py"
        ).read_text()
        assert "except Exception" in src, (
            "log_event must catch a broad Exception around the "
            "SAVEPOINT block — any error here must be advisory."
        )
        assert "logger.warning" in src, (
            "Swallowed exceptions must be logged so silent failures "
            "are still traceable in production logs."
        )


# ═════════════════════════════════════════════════════════════════════
# 4. Default values — caller convenience
# ═════════════════════════════════════════════════════════════════════

class TestLogEventDefaults:
    """Most callers pass only event_type. The function must default
    actor='pipeline' and commit=False so a script-author who forgets
    to pass commit=True doesn't accidentally hold a transaction open
    indefinitely."""

    @pytest.mark.asyncio
    async def test_default_actor_pipeline(self):
        @asynccontextmanager
        async def fake_savepoint():
            yield

        db = MagicMock()
        db.begin_nested = MagicMock(return_value=fake_savepoint())
        db.execute = AsyncMock()

        await log_event(db, event_type="x")

        # The bound params dict is the second positional arg to execute.
        params = db.execute.call_args.args[1]
        assert params["actor"] == "pipeline"

    @pytest.mark.asyncio
    async def test_default_no_commit(self):
        """Default `commit=False` — let the caller's transaction
        carry the row. Otherwise scripts can accidentally fragment
        their batched work into single-row commits."""
        @asynccontextmanager
        async def fake_savepoint():
            yield

        db = MagicMock()
        db.begin_nested = MagicMock(return_value=fake_savepoint())
        db.execute = AsyncMock()
        db.commit = AsyncMock()

        await log_event(db, event_type="x")

        # commit must NOT have been called.
        db.commit.assert_not_called()
