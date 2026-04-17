"""Shared in-memory state for a running /admin/force-resummarize job.

The endpoint used to block the HTTP request for the full duration of
the loop (one LLM call per story, 20-40s each), which means a 16-story
run needs 8-10 minutes. Cloudflare's edge proxy terminates idle HTTP
connections after 100s, so the client got "Load failed" before the
backend finished. Now the endpoint kicks off a background task and
returns immediately with a job id; the frontend polls this state
dict to show progress.

Not durable — resets on backend restart. If Railway redeploys
mid-run the job is lost; the next status poll returns `status=idle`
and the frontend can show an error.
"""

import time
from datetime import datetime, timezone
from typing import Any


STATE: dict = {
    "status": "idle",           # idle | running | success | error
    "job_id": None,
    "started_at": None,         # unix timestamp
    "finished_at": None,
    "elapsed_s": None,
    "total": 0,                 # how many stories in the batch
    "processed": 0,             # how many completed (success or failure)
    "regenerated": 0,           # successful rewrites
    "failed": 0,                # failed rewrites
    "current_story_title": None,
    "model": None,
    "errors": [],
    "story_ids": [],            # ids in the batch, in processing order
    "error": None,              # fatal error that aborted the job
}


def start_job(total: int, story_ids: list[str], model: str) -> str:
    """Reset state for a new run and return a job id."""
    import uuid
    job_id = str(uuid.uuid4())
    STATE.update(
        status="running",
        job_id=job_id,
        started_at=time.time(),
        finished_at=None,
        elapsed_s=None,
        total=total,
        processed=0,
        regenerated=0,
        failed=0,
        current_story_title=None,
        model=model,
        errors=[],
        story_ids=story_ids,
        error=None,
    )
    return job_id


def mark_story_start(title: str) -> None:
    STATE["current_story_title"] = title


def mark_story_done(success: bool, error_msg: str | None = None) -> None:
    STATE["processed"] = STATE.get("processed", 0) + 1
    if success:
        STATE["regenerated"] = STATE.get("regenerated", 0) + 1
    else:
        STATE["failed"] = STATE.get("failed", 0) + 1
        if error_msg:
            errs = STATE.get("errors") or []
            errs.append(error_msg)
            STATE["errors"] = errs[-10:]  # keep last 10 only


def finish_job(error: str | None = None) -> None:
    started = STATE.get("started_at")
    STATE["finished_at"] = time.time()
    STATE["elapsed_s"] = (
        round(STATE["finished_at"] - started, 1) if started else None
    )
    STATE["current_story_title"] = None
    if error:
        STATE["status"] = "error"
        STATE["error"] = error
    else:
        STATE["status"] = "success"


def snapshot() -> dict:
    """Return a copy safe to JSON-serialize."""
    s = dict(STATE)
    # ISO-format timestamps for readability
    if s.get("started_at"):
        s["started_at_iso"] = datetime.fromtimestamp(s["started_at"], tz=timezone.utc).isoformat()
    if s.get("finished_at"):
        s["finished_at_iso"] = datetime.fromtimestamp(s["finished_at"], tz=timezone.utc).isoformat()
    # Live elapsed while running
    if s["status"] == "running" and s.get("started_at"):
        s["elapsed_s"] = round(time.time() - s["started_at"], 1)
    return s
