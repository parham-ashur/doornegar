"""Multi-locale translation pipeline (EN+FR rollout Phase 2).

Translates Persian story content (title, summary) into English (NYT
register) and French (Le Monde register) using gpt-4o-mini for the
editorial tier. Voice prompts live as plain text files in the
`voice_prompts/` subdirectory; load them at call time.

This module is separate from `translation.py` (which is the legacy
Helsinki-NLP FA↔EN article-title backfill used by nlp_pipeline).
Different purpose, different model, different cost ledger purpose tag.

Design rules followed:
- Short DB session (CLAUDE.md / Audit 3): read → close → translate
  (no session held) → fresh-session writes. Mirrors
  bias_scoring.score_unscored_articles.
- No silent fallbacks (feedback_no_silent_fallbacks): all error paths
  return None; never empty string, never the FA original, never a
  placeholder.
- Sentinel-trap aware (feedback_processed_at_trap): re-translation
  retries stories where translations.{locale}.translated_at <
  story.updated_at AND is_edited is False. Manual edits
  (is_edited=True) are never overwritten.
- Homepage-eligible only (project_homepage_scoping): calls
  homepage_story_ids() before any LLM cost.
- Spend-priority sort (feedback_spend_priority_sort): order by
  priority DESC, trending_score DESC.
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

from sqlalchemy import select
from sqlalchemy import text as _sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.database import async_session
from app.models.story import Story
from app.services.homepage_scope import homepage_story_ids
from app.services.llm_usage import log_llm_usage

logger = logging.getLogger(__name__)

TRANSLATION_FAILED_SENTINEL = "[TRANSLATION_FAILED]"

_VOICE_PROMPTS_DIR = Path(__file__).parent / "voice_prompts"

EDITORIAL_MODEL = (
    getattr(settings, "translation_editorial_model", None) or "gpt-4o-mini"
)

PROMPT_VERSIONS: dict[str, str] = {
    "en": "nyt-v1",
    "fr": "lemonde-v1",
}

OG_LOCALES = ("en", "fr")

_EDITORIAL_SEMAPHORE = asyncio.Semaphore(8)

STORIES_PER_RUN = int(
    getattr(settings, "translation_stories_per_run", None) or 30
)

COST_CAP_USD_24H = float(
    getattr(settings, "translation_cost_cap_usd_24h", None) or 1.0
)

STALE_LOOKBACK_DAYS = 14


def _load_prompt(version: str) -> str:
    """Load a voice prompt by version. Cached after first read."""
    cache = _load_prompt._cache  # type: ignore[attr-defined]
    if version in cache:
        return cache[version]
    path = _VOICE_PROMPTS_DIR / f"{version}.txt"
    text = path.read_text(encoding="utf-8")
    cache[version] = text
    return text


_load_prompt._cache = {}  # type: ignore[attr-defined]


async def _check_cost_breaker(db: AsyncSession) -> tuple[bool, float]:
    """Return (under_cap, current_24h_cost_usd)."""
    cost = float(
        (
            await db.execute(
                _sa_text(
                    "SELECT COALESCE(SUM(total_cost), 0) FROM llm_usage_logs "
                    "WHERE purpose LIKE 'translation\\_%' ESCAPE '\\' "
                    "AND timestamp >= NOW() - INTERVAL '24 hours'"
                )
            )
        ).scalar()
        or 0.0
    )
    return cost < COST_CAP_USD_24H, cost


def _compose_user_message(payload: dict[str, str]) -> str:
    """Compose a JSON-shaped user prompt.

    The LLM is invoked with response_format={"type": "json_object"},
    which constrains it to return valid JSON matching the requested
    schema. The ### key block format from the first iteration was too
    fragile — gpt-4o-mini ignored markers when prompted in French
    (100% parse failure on FR in the 2026-05-07 09:00 UTC cron).
    """
    import json as _json
    parts = ["Translate each non-empty field. Return JSON with the same keys."]
    payload_clean = {
        k: (v or "").strip()
        for k, v in payload.items()
        if (v or "").strip()
    }
    if not payload_clean:
        return ""
    parts.append("Input:")
    parts.append(_json.dumps(payload_clean, ensure_ascii=False))
    parts.append(
        "Output a JSON object with exactly these keys: "
        + ", ".join(payload_clean.keys())
        + ". No markdown, no commentary, no extra fields."
    )
    return "\n\n".join(parts)


def _parse_structured(
    output: str, expected_keys: Iterable[str]
) -> dict[str, str] | None:
    """Parse a JSON object response. With response_format=json_object
    the LLM is constrained to valid JSON, so this is straightforward.
    Falls back to None on any parse failure (no silent fallbacks)."""
    if not output:
        return None
    import json as _json
    text = output.strip()
    # Strip markdown code fences if the model added them despite
    # the json_object response_format (occasional behavior).
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = _json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    expected = {k.lower() for k in expected_keys}
    out: dict[str, str] = {}
    for key, value in parsed.items():
        k = str(key).strip().lower()
        if k in expected and isinstance(value, str) and value.strip():
            out[k] = value.strip()
    if not out:
        return None
    return out


async def _log_failure(
    *, purpose: str, story_id, error: str, model: str = EDITORIAL_MODEL
) -> None:
    try:
        await log_llm_usage(
            model=model,
            purpose=purpose,
            input_tokens=0,
            output_tokens=0,
            story_id=story_id,
            meta={"failed": "true", "error": error[:200]},
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to log translation failure to cost ledger")


async def translate_story(
    *,
    story_id,
    fa_payload: dict[str, str],
    locale: Literal["en", "fr"],
    prompt_version: str | None = None,
) -> dict[str, str] | None:
    """Translate one Persian payload to the target locale.

    Returns the translated payload dict, or None on any failure
    (silent fallbacks are forbidden — callers must distinguish None
    from empty).
    """
    if not settings.openai_api_key:
        return None
    if locale not in PROMPT_VERSIONS:
        return None

    version = prompt_version or PROMPT_VERSIONS[locale]
    try:
        system_prompt = _load_prompt(version)
    except FileNotFoundError:
        logger.error(f"Voice prompt missing: {version}")
        return None

    user_msg = _compose_user_message(fa_payload)
    if not user_msg:
        return None

    purpose = f"translation_{locale}"
    import openai

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    response = None
    last_error: str | None = None
    async with _EDITORIAL_SEMAPHORE:
        for attempt in range(3):
            try:
                response = await client.chat.completions.create(
                    model=EDITORIAL_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0,
                    max_tokens=3000,
                    response_format={"type": "json_object"},
                )
                break
            except openai.RateLimitError as e:
                last_error = f"rate_limit:{e}"
                if attempt == 2:
                    break
                await asyncio.sleep(0.75 * (2**attempt))
            except (openai.APIError, openai.APIConnectionError) as e:
                last_error = f"api_error:{e}"
                if attempt == 2:
                    break
                await asyncio.sleep(0.75 * (2**attempt))
            except Exception as e:  # noqa: BLE001
                last_error = f"unexpected:{e!r}"
                break

    if response is None:
        await _log_failure(
            purpose=purpose, story_id=story_id, error=last_error or "no response"
        )
        return None

    output = response.choices[0].message.content or ""
    await log_llm_usage(
        model=EDITORIAL_MODEL,
        purpose=purpose,
        usage=response.usage,
        story_id=story_id,
        meta={"prompt_version": version},
    )

    if TRANSLATION_FAILED_SENTINEL in output:
        logger.info(f"Translation refusal for story {story_id} {locale}")
        await _log_failure(
            purpose=purpose, story_id=story_id, error="refusal_sentinel"
        )
        return None

    parsed = _parse_structured(output, fa_payload.keys())
    if parsed is None:
        logger.warning(
            f"Translation parse failed for story {story_id} {locale} ({len(output)} chars)"
        )
        await _log_failure(
            purpose=purpose, story_id=story_id, error="parse_failed"
        )
        return None

    return parsed


async def step_translate_homepage_visible() -> dict[str, Any]:
    """Maintenance step: translate up to STORIES_PER_RUN homepage stories."""
    if not settings.openai_api_key:
        return {"skipped": True, "reason": "no openai key"}

    now_utc = datetime.now(timezone.utc)

    async with async_session() as db:
        under_cap, current_cost = await _check_cost_breaker(db)
        if not under_cap:
            return {
                "skipped": True,
                "reason": "cost_breaker",
                "cost_24h_usd": round(current_cost, 4),
            }

        homepage_ids = await homepage_story_ids(db)
        if not homepage_ids:
            return {
                "checked": 0,
                "translated": {"en": 0, "fr": 0},
                "failed": 0,
                "cost_breaker": False,
            }

        candidates = (
            await db.execute(
                select(Story)
                .where(
                    Story.id.in_(homepage_ids),
                    Story.title_fa.is_not(None),
                    _sa_text(
                        "(translations IS NULL "
                        " OR translations->'en' IS NULL "
                        " OR translations->'fr' IS NULL "
                        " OR (translations->'en'->>'translated_at')::timestamptz "
                        "    < COALESCE(updated_at, created_at) "
                        " OR (translations->'fr'->>'translated_at')::timestamptz "
                        "    < COALESCE(updated_at, created_at)) "
                    ),
                )
                .order_by(Story.priority.desc(), Story.trending_score.desc())
                .limit(STORIES_PER_RUN)
            )
        ).scalars().all()

        snapshots = [
            {
                "id": s.id,
                "title_fa": s.title_fa or "",
                "summary_fa": s.summary_fa or "",
                "translations": dict(s.translations or {}),
                "updated_at": s.updated_at or s.created_at,
            }
            for s in candidates
        ]

    if not snapshots:
        return {
            "checked": 0,
            "translated": {"en": 0, "fr": 0},
            "failed": 0,
            "cost_breaker": False,
        }

    work: list[tuple[dict[str, Any], str]] = []
    for snap in snapshots:
        for locale in OG_LOCALES:
            existing = (snap["translations"].get(locale) or {})
            if existing.get("is_edited"):
                continue
            translated_at = existing.get("translated_at")
            needs = False
            if not translated_at:
                needs = True
            else:
                try:
                    ta = datetime.fromisoformat(
                        translated_at.replace("Z", "+00:00")
                    )
                    if ta.tzinfo is None:
                        ta = ta.replace(tzinfo=timezone.utc)
                    if ta < snap["updated_at"]:
                        age_days = (now_utc - snap["updated_at"]).days
                        if age_days <= STALE_LOOKBACK_DAYS:
                            needs = True
                except (ValueError, AttributeError):
                    needs = True
            if needs:
                work.append((snap, locale))

    if not work:
        return {
            "checked": len(snapshots),
            "translated": {"en": 0, "fr": 0},
            "failed": 0,
            "cost_breaker": False,
        }

    successes: dict[str, list[tuple[Any, dict[str, str]]]] = {"en": [], "fr": []}
    failures = 0
    failure_lock = asyncio.Lock()

    async def _do_one(snap, locale):
        nonlocal failures
        fa_payload = {"title": snap["title_fa"], "summary": snap["summary_fa"]}
        result = await translate_story(
            story_id=snap["id"], fa_payload=fa_payload, locale=locale
        )
        if result is None:
            async with failure_lock:
                failures += 1
            return
        successes[locale].append((snap["id"], result))

    await asyncio.gather(
        *(_do_one(snap, locale) for snap, locale in work),
        return_exceptions=False,
    )

    if not successes["en"] and not successes["fr"]:
        return {
            "checked": len(snapshots),
            "translated": {"en": 0, "fr": 0},
            "failed": failures,
            "cost_breaker": False,
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    async with async_session() as db:
        for locale in OG_LOCALES:
            for story_id, translated in successes[locale]:
                story = await db.get(Story, story_id)
                if not story:
                    continue
                blob = dict(story.translations or {})
                slot = dict(blob.get(locale) or {})
                if slot.get("is_edited"):
                    continue
                slot.update(translated)
                slot["translated_at"] = now_iso
                slot["prompt_version"] = PROMPT_VERSIONS[locale]
                slot["is_edited"] = False
                blob[locale] = slot
                story.translations = blob
                # SQLAlchemy doesn't detect mutations of JSONB dict
                # values as dirty unless we flag them explicitly. The
                # cron's first run silently committed nothing without
                # this — 30 successful LLM calls produced 0 persisted
                # rows (2026-05-07 09:00 UTC cron diagnosed).
                flag_modified(story, "translations")
        await db.commit()

    return {
        "checked": len(snapshots),
        "translated": {"en": len(successes["en"]), "fr": len(successes["fr"])},
        "failed": failures,
        "cost_breaker": False,
        "cost_24h_usd_before": round(current_cost, 4),
    }


async def clear_translations_for_story(
    db: AsyncSession,
    story_id,
    *,
    locales: Iterable[str] | None = None,
) -> None:
    """Auto-clear hook called by editing endpoints when FA content changes.

    Per the Re-translate trigger map. Caller commits the surrounding
    transaction; this function only mutates the story.translations
    field in-session.
    """
    targets = list(locales) if locales else list(OG_LOCALES)
    story = await db.get(Story, story_id)
    if not story or not story.translations:
        return
    blob = dict(story.translations)
    changed = False
    for locale in targets:
        slot = blob.get(locale)
        if not slot:
            continue
        if slot.get("is_edited"):
            continue
        del blob[locale]
        changed = True
    if changed:
        story.translations = blob if blob else None
        flag_modified(story, "translations")
