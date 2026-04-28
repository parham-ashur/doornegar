"""Cross-process maintenance status, mirrored to a tmpfile.

Both auto_maintenance.py (which runs the steps) and app/api/v1/admin.py
(which exposes the status endpoint) import from this module. The 2026-04-28
incident showed why in-memory STATE alone is insufficient: the dashboard
"Run now" path was changed to spawn a detached subprocess so it doesn't
starve the API event loop, and the subprocess's STATE dict is invisible
to the API process. The API's /admin/maintenance/status used to be a
read-only mirror of the live STATE; now it reads from `_STATUS_PATH` so
both processes converge on the same source of truth.

We mirror to /tmp because the API container and the maintenance
subprocess share the same filesystem (they run on the same Railway
container). For Railway-managed restarts the file is wiped, which is
fine — the dashboard already falls back to maintenance_logs for
historical context, and the live state is only relevant during a run.

The file is JSON, written atomically via a tmpfile + os.replace. The
read side accepts a missing/corrupt file as "idle".
"""

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_STATUS_PATH = Path(os.environ.get("DOORNEGAR_MAINT_STATUS_PATH",
                                   "/tmp/doornegar_maintenance_status.json"))

# Throttle file writes to avoid spamming on tight progress callbacks.
# Begin/end transitions always flush; only fine-grained progress is throttled.
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


def _flush(force: bool = False) -> None:
    """Write the current STATE to `_STATUS_PATH` atomically.

    `force=True` bypasses the 1s throttle — used for begin/end transitions
    where the caller cares about timeliness more than frequency.
    """
    global _LAST_WRITE_TS
    now = time.time()
    if not force and (now - _LAST_WRITE_TS) < _WRITE_THROTTLE_SEC:
        return
    _LAST_WRITE_TS = now
    try:
        _STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, dir=str(_STATUS_PATH.parent),
            prefix=".doornegar_maint_", suffix=".tmp", encoding="utf-8",
        ) as f:
            json.dump(STATE, f, ensure_ascii=False, default=str)
            tmp_path = f.name
        os.replace(tmp_path, _STATUS_PATH)
    except Exception:
        # Best-effort. A failed mirror just means the dashboard sees
        # stale or no live state; the run itself isn't affected.
        pass


def read_persisted() -> dict | None:
    """Return the STATE dict from the tmpfile, or None if unavailable.

    Used by the API process to see what the maintenance subprocess (on
    the same container, different PID) is doing. Returns None on read
    error so the caller can fall back to the in-memory STATE (e.g.,
    when the cron service runs on a different container and writes
    nothing locally).
    """
    try:
        if not _STATUS_PATH.is_file():
            return None
        with _STATUS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
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
    can show a fraction (e.g., "Migrate images: 47/300"). Pure in-memory
    update on the same Python process that runs the step — never touches
    the DB or Redis. Safe to call frequently.

    The mirror to `_STATUS_PATH` is throttled to 1s so high-frequency
    progress callbacks don't thrash the disk.
    """
    STATE["current_step_progress"] = {
        "done": int(done),
        "total": int(total),
        "label": label,
    }
    _flush(force=False)  # throttled — progress can fire many times/second


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
    import json
    try:
        json.dumps(obj)
        return True
    except Exception:
        return False
