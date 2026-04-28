"""Shared in-memory state for the currently-running maintenance cycle.

Both auto_maintenance.py (which runs the steps) and app/api/v1/admin.py
(which exposes the status endpoint) import from this module so the
frontend can poll a single source of truth.

Not durable — resets on backend restart. That's fine; the dashboard
only cares about what's happening right now.
"""

import time
from datetime import datetime, timezone
from typing import Any


# Global state dict for the current or most-recent maintenance run
STATE: dict = {
    "status": "idle",           # idle | running | success | error
    "started_at": None,
    "finished_at": None,
    "elapsed_s": None,
    "current_step": None,        # name of step currently running, if any
    "current_step_started": None,  # monotonic time current step began
    "steps": [],                 # list of {name, status, elapsed_s, stats}
    "results": None,             # final results dict from run_maintenance
    "error": None,
}


def start_run(total_steps: int = 14) -> None:
    """Reset state and mark a new run as started."""
    STATE.update({
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "elapsed_s": None,
        "current_step": None,
        "current_step_started": None,
        "steps": [],
        "results": None,
        "error": None,
        "total_steps": total_steps,
    })


def begin_step(name: str) -> None:
    """Mark a step as starting."""
    STATE["current_step"] = name
    STATE["current_step_started"] = time.time()
    STATE["current_step_progress"] = None


def update_step_progress(done: int, total: int, label: str | None = None) -> None:
    """Long-running steps call this from their inner loop so the dashboard
    can show a fraction (e.g., "Migrate images: 47/300"). Pure in-memory
    update on the same Python process that runs the step — never touches
    the DB or Redis. Safe to call frequently.
    """
    STATE["current_step_progress"] = {
        "done": int(done),
        "total": int(total),
        "label": label,
    }


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


def finish_run(status: str, results: Any = None, error: str | None = None, total_elapsed_s: float | None = None) -> None:
    """Mark the whole run as done."""
    STATE.update({
        "status": status,  # success | error
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(total_elapsed_s, 1) if total_elapsed_s is not None else None,
        "current_step": None,
        "current_step_started": None,
        "results": results if _is_jsonable(results) else str(results),
        "error": error,
    })


def _is_jsonable(obj: Any) -> bool:
    """Best-effort check that obj survives JSON serialization."""
    import json
    try:
        json.dumps(obj)
        return True
    except Exception:
        return False
