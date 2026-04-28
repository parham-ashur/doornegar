"""Cross-process maintenance status, mirrored to a DB row.

Both auto_maintenance.py (which runs the steps) and app/api/v1/admin.py
(which exposes the status endpoint) import from this module.

Design history (2026-04-28):
- v1: in-memory STATE only. Broke when /admin/maintenance/run was
  changed to spawn a subprocess (different process, different memory).
- v2: mirror to /tmp file. Didn't work on Railway — likely private-tmp
  namespace per process.
- v3: mirror to single-row DB table via fire-and-forget asyncio tasks.
  Tasks weren't running — either GC'd before scheduling or the event
  loop wasn't yielding enough during ingest's HTTP-heavy work.
- v4 (current): make the transition functions async so writes happen
  synchronously inline. Adds ~50ms per transition (one round trip to
  Neon). Begin/end transitions are the only frequent writers; the
  per-iteration progress updates are throttled to 1s. Total overhead
  is negligible compared to the LLM-heavy steps.

The /admin/maintenance/status endpoint awaits read_persisted() to
fetch the current state, falling back to in-memory STATE only when
the DB row is empty/idle.
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
    "current_step": None,
    "current_step_started": None,
    "current_step_progress": None,
    "steps": [],
    "results": None,
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


async def _flush(force: bool = False) -> None:
    """Mirror STATE to the DB. Throttled to 1s unless force=True.

    Now async — writes happen inline so callers can be confident the
    state is durable before they proceed. Failures are logged at
    WARNING and swallowed (best-effort mirror).
    """
    global _LAST_WRITE_TS
    now = time.time()
    if not force and (now - _LAST_WRITE_TS) < _WRITE_THROTTLE_SEC:
        return
    _LAST_WRITE_TS = now
    snapshot = dict(STATE)
    try:
        await _write_state(snapshot)
    except Exception as e:
        import logging as _log
        _log.getLogger(__name__).warning(
            "maintenance_state mirror write failed: %s", e
        )


async def read_persisted() -> dict | None:
    """Return the state from the DB row, or None if unavailable."""
    try:
        from sqlalchemy import text as _t
        from app.database import async_session
        async with async_session() as db:
            row = (await db.execute(_t(
                "SELECT state, updated_at FROM maintenance_run_status WHERE id = 1"
            ))).first()
        if not row or not row.state:
            return None
        s = row.state if isinstance(row.state, dict) else json.loads(row.state)
        if isinstance(s, dict):
            s["_status_updated_at"] = row.updated_at.isoformat() if row.updated_at else None
        return s
    except Exception:
        return None


async def start_run(total_steps: int = 14) -> None:
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
    await _flush(force=True)


async def begin_step(name: str) -> None:
    """Mark a step as starting."""
    STATE["current_step"] = name
    STATE["current_step_started"] = time.time()
    STATE["current_step_progress"] = None
    await _flush(force=True)


async def update_step_progress(done: int, total: int, label: str | None = None) -> None:
    """Long-running steps call this from their inner loop. Throttled to 1s
    so high-frequency progress callbacks don't thrash the DB."""
    STATE["current_step_progress"] = {
        "done": int(done),
        "total": int(total),
        "label": label,
    }
    await _flush(force=False)


async def end_step(name: str, status: str, stats: Any = None) -> None:
    """Mark a step as finished (success or error) and record it."""
    started = STATE.get("current_step_started") or time.time()
    elapsed = round(time.time() - started, 1)
    STATE["steps"].append({
        "name": name,
        "status": status,
        "elapsed_s": elapsed,
        "stats": stats if _is_jsonable(stats) else str(stats),
    })
    STATE["current_step"] = None
    STATE["current_step_started"] = None
    STATE["current_step_progress"] = None
    await _flush(force=True)


async def finish_run(status: str, results: Any = None, error: str | None = None, total_elapsed_s: float | None = None) -> None:
    """Mark the whole run as done."""
    STATE.update({
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(total_elapsed_s, 1) if total_elapsed_s is not None else None,
        "current_step": None,
        "current_step_started": None,
        "current_step_progress": None,
        "results": results if _is_jsonable(results) else str(results),
        "error": error,
    })
    await _flush(force=True)


def _is_jsonable(obj: Any) -> bool:
    """Best-effort check that obj survives JSON serialization."""
    try:
        json.dumps(obj, default=str)
        return True
    except Exception:
        return False
