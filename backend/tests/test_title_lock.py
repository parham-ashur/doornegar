"""Editorial title-lock regression tests.

Bug (2026-06-23): an admin corrects a propaganda headline via PATCH
/admin/stories/{id} — the corrected title is written to
`summary_anchor['title_fa']` — but the cron's summarize / quality steps
regenerated the title every run and, on state-media-heavy clusters, drifted
it back to the original framing («پیروزی ایران» asserted as fact). The fix
locks the title to the anchor in all three title-writing pipeline steps.

These tests pin both the helper's behavior and that the three call sites
stay wired (a source-level tripwire — the steps are too heavy to exercise
end-to-end here).
"""
import re
from pathlib import Path
from types import SimpleNamespace

from app.services.story_analysis import locked_title


def test_locked_title_returns_anchored_title():
    story = SimpleNamespace(
        summary_anchor={"title_fa": "عنوان اصلاح‌شده سردبیر", "summary_fa": "x"}
    )
    assert locked_title(story) == "عنوان اصلاح‌شده سردبیر"


def test_locked_title_strips_whitespace():
    story = SimpleNamespace(summary_anchor={"title_fa": "  لنگر  "})
    assert locked_title(story) == "لنگر"


def test_locked_title_none_when_no_anchor():
    assert locked_title(SimpleNamespace(summary_anchor=None)) is None


def test_locked_title_none_when_anchor_has_no_title():
    # An anchor that pins only the body (no title) must NOT lock the title.
    story = SimpleNamespace(summary_anchor={"summary_fa": "فقط متن"})
    assert locked_title(story) is None


def test_locked_title_none_when_title_blank():
    assert locked_title(SimpleNamespace(summary_anchor={"title_fa": "   "})) is None


def test_locked_title_handles_non_dict_anchor():
    # JSONB column could in theory be a stray scalar/list — must not raise.
    assert locked_title(SimpleNamespace(summary_anchor="oops")) is None
    assert locked_title(SimpleNamespace(summary_anchor=[1, 2])) is None


def test_all_three_pipeline_steps_wire_the_lock():
    """Tripwire: every cron step that writes story.title_fa must consult
    locked_title. There are exactly three (summarize_newly_visible,
    summarize, quality_postprocess); if a new title-writer is added it must
    honor the lock too — bump this count and guard the new site."""
    src = (Path(__file__).resolve().parent.parent / "auto_maintenance.py").read_text(
        encoding="utf-8"
    )
    # All story-title assignments in the pipeline: 3 LLM/QC-sourced writes
    # (the ones that must be guarded) + 2 lock-application writes (the
    # `story.title_fa = _lock` branches) = 5.
    title_writes = len(re.findall(r"\bstory\.title_fa\s*=", src))
    # One guard import per title-writing step (`locked_title as _locked_title*`).
    lock_refs = len(re.findall(r"locked_title as _locked_title", src))
    assert lock_refs == 3, (
        f"expected the title-lock guard wired at all 3 title-writing steps, "
        f"found {lock_refs}; a new title-writer must consult locked_title()"
    )
    assert title_writes == 5, (
        f"expected 5 story.title_fa assignments (3 sourced + 2 lock branches) "
        f"in auto_maintenance.py, found {title_writes}; a new title-writer "
        f"changed this — guard it with locked_title() and update this count"
    )
