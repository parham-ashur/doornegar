"""Cross-process maintenance status, mirrored to a DB row.

Both auto_maintenance.py (which runs the steps) and app/api/v1/admin.py
(which exposes the status endpoint) import from this module. The
dashboard's "Run now" path spawns maintenance as a subprocess so it
doesn't starve the API event loop. The subprocess's STATE dict is
invisible to the API process, so we mirror to a single-row
`maintenance_run_status` table.

Earlier (2026-04-28 morning) we tried mirroring to /tmp; that didn't
surface to the API on Railway — likely a private-tmp namespace between
subprocess and the API process. DB-backed mirror works regardless of
process or container boundaries.

The mirror runs `asyncio.run(...)` to open a fresh asyncpg connection
per write — the maintenance_state functions are sync (begin_step,
end_step, update_step_progress) and called from various async contexts,
so we can't trivially make them async without changing every call site.
A short-lived connection per flush is fine; the writes are throttled
to 1s for high-frequency progress callbacks. Begin/end transitions
flush immediately.
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any


_LAST_WRITE_TS = 0.0
_WRITE_THROTTLE_SEC = 1.0


# Global state dict for the current or most-recent maintenance run
STATE: dict = {
    "status": "idle",           # idle | running | success | error
    "started_at": None,
    "finished_at": None,
    "elapsed_s": None,
    "current_step": None,        # name of step currently running, if any
    "current_step_started": None,  # monotonic time current step began
    "current_step_progress": None,  # {done, total, label}
    "steps": [],                 # list of {name, status, elapsed_s, stats}
    "results": None,             # final results dict from run_maintenance
    "error": None,
}


async def _write_state(snapshot: dict) -> None:
    """Write the snapshot to the maintenance_run_status row."""
    from sqlalchemy import text as _t
    from app.database import async_session
    payload = json.dumps(snapshot, ensure_ascii=False, default=str)
    async with async_session() as db:
        await db.execute(_t(
            "INSERT INTO maintenance_run_status (id, state, updated_at) "
            "VALUES (1, CAST(:state AS jsonb), NOW()) "
            "ON CONFLICT (id) DO UPDATE SET state = EXCLUDED.state, updated_at = NOW()"
        ), {"state": payload})
        await db.commit()


def _flush(force: bool = False) -> None:
    """Mirror STATE to the DB. Throttled to 1s unless force=True.

    Best-effort — a failed mirror just means the dashboard sees stale
    state for a tick. The run itself isn't affected.
    """
    global _LAST_WRITE_TS
    now = time.time()
    if not force and (now - _LAST_WRITE_TS) < _WRITE_THROTTLE_SEC:
        return
    _LAST_WRITE_TS = now
    snapshot = dict(STATE)
    try:
        # Use asyncio.run when called from a sync context (no running loop).
        # When called from inside an event loop (the maintenance subprocess
        # IS async), schedule the write as a task instead so we don't try
        # to nest asyncio.run.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            asyncio.run(_write_state(snapshot))
        else:
            # Fire-and-forget within the running loop; the write completes
            # asynchronously without blocking the caller. Errors land in
            # the task and are silently dropped (best-effort mirror).
            loop.create_task(_write_state(snapshot))
    except Exception:
        pass


async def read_persisted() -> dict | None:
    """Return the state from the DB row, or None if unavailable.

    Used by the API process to see what a maintenance subprocess (or
    the cron container) is doing. Returns None on read error so the
    caller can fall back to the in-memory STATE.
    """
    try:
        from sqlalchemy import text as _t
        from app.database import async_session
        async with async_session() as db:
            row = (await db.execute(_t(
                "SELECT state, updated_at FROM maintenance_run_status WHERE id = 1"
            ))).first()
        if not row or not row.state:
            return None
        # state column is JSONB — asyncpg returns it as a dict already.
        s = row.state if isinstance(row.state, dict) else json.loads(row.state)
        if isinstance(s, dict):
            s["_status_updated_at"] = row.updated_at.isoformat() if row.updated_at else None
        return s
    except Exception:
        return None


def start_run(total_steps: int = 14) -> None:
    """Reset state and mark a new run as started."""
    STATE.update({
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "elapsed_s": None,
        "current_step": None,
        "current_step_started": None,
        "current_step_progress": None,
        "steps": [],
        "results": None,
        "error": None,
        "total_steps": total_steps,
        "pid": os.getpid(),
    })
    _flush(force=True)


def begin_step(name: str) -> None:
    """Mark a step as starting."""
    STATE["current_step"] = name
    STATE["current_step_started"] = time.time()
    STATE["current_step_progress"] = None
    _flush(force=True)


def update_step_progress(done: int, total: int, label: str | None = None) -> None:
    """Long-running steps call this from their inner loop so the dashboard
    can show a fraction (e.g., "Migrate images: 47/300"). The mirror to
    the DB is throttled to 1s so high-frequency progress callbacks don't
    spam the database.
    """
    STATE["current_step_progress"] = {
        "done": int(done),
        "total": int(total),
        "label": label,
    }
    _flush(force=False)


def end_step(name: str, status: str, stats: Any = None) -> None:
    """Mark a step as finished (success or error) and record it."""
    started = STATE.get("current_step_started") or time.time()
    elapsed = round(time.time() - started, 1)
    STATE["steps"].append({
        "name": name,
        "status": status,  # ok | error
        "elapsed_s": elapsed,
        "stats": stats if _is_jsonable(stats) else str(stats),
    })
    STATE["current_step"] = None
    STATE["current_step_started"] = None
    STATE["current_step_progress"] = None
    _flush(force=True)


def finish_run(status: str, results: Any = None, error: str | None = None, total_elapsed_s: float | None = None) -> None:
    """Mark the whole run as done."""
    STATE.update({
        "status": status,  # success | error
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(total_elapsed_s, 1) if total_elapsed_s is not None else None,
        "current_step": None,
        "current_step_started": None,
        "current_step_progress": None,
        "results": results if _is_jsonable(results) else str(results),
        "error": error,
    })
    _flush(force=True)


def _is_jsonable(obj: Any) -> bool:
    """Best-effort check that obj survives JSON serialization."""
    try:
        json.dumps(obj, default=str)
        return True
    except Exception:
        return False
