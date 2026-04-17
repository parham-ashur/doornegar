# i18n Plan — English + French, with full RTL ↔ LTR flip

**Status**: Planned, not started
**Written**: 2026-04-17
**Owner**: Parham (product) / Claude (implementation)

## Context

Today Doornegar ships Farsi-only (`/fa/...`). The Next.js App Router
already uses `[locale]` in the route tree and `next-intl` is wired up,
but:
- Every visible string is a hardcoded Farsi literal in JSX.
- The `<html>` has no `dir` attribute; several divs pin `dir="rtl"`.
- Tailwind classes across the codebase use physical directions
  (`pr-*`, `ml-*`, `text-right`, `border-l`) that do NOT auto-flip.

We want English and French users to see:
- Chrome (buttons, labels, tabs, nav, stats) in their language.
- Page layout mirrored for LTR — the Telegram box, blindspot cards,
  and stats sidebar naturally flip to the opposite side.
- (Optional later) Story summaries + bias explanations also translated.

The work splits into three tiers. Tier 1 is a ~1-day job and ships the
localized shell; Tier 2 is a multi-week project that localizes the
editorial content itself.

---

## Tier 1 — UI chrome localization + LTR support

**Scope**: every user-facing label, button, tab, stat name, tooltip,
nav item. Story titles and summaries stay in Farsi regardless of UI
locale (same model as BBC Persian / DW Persian / Iran International).

**Estimated effort**: ~8–16 hours of focused implementation.

### Commit 1 — Logical CSS refactor (~2 hours)

**Why first**: once this is done, LTR layout works automatically for
almost every component. Changes nothing visually in Farsi — the site
looks identical today after this commit.

**What to change**:

1. **`<html>` dir attribute** — `app/[locale]/layout.tsx` sets
   `dir={locale === "fa" ? "rtl" : "ltr"}` on the root element and
   removes any child `dir="rtl"` hardcodes.
2. **Hardcoded `dir="rtl"`** on inner divs — remove, or make
   conditional via `useLocale()` where a div must override for any
   reason.
3. **Replace physical Tailwind classes**:
   | Physical | Logical |
   |---|---|
   | `text-left` | `text-start` |
   | `text-right` | `text-end` |
   | `pl-*`, `pr-*` | `ps-*`, `pe-*` |
   | `ml-*`, `mr-*` | `ms-*`, `me-*` |
   | `border-l`, `border-r` | `border-s`, `border-e` |
   | `rounded-l-*`, `rounded-r-*` | `rounded-s-*`, `rounded-e-*` |
   | `left-*`, `right-*` (absolute positioning) | `start-*`, `end-*` |
   | `order-1`, `order-2` | `order-first`, `order-last` |
4. **Coverage bar direction** — already fine if using flex (flips
   automatically). Audit the homepage hero grid (`grid-cols-2` narrative
   cards) and story detail layout (`grid-cols-1 lg:grid-cols-2` two-column).

### The layouts that MUST mirror correctly (sanity checklist)

These are the places where the column swap is user-visible. When LTR
looks right here, the whole Tier 1 pass is done.

#### Story detail page — `app/[locale]/stories/[id]/page.tsx`

```
Farsi (RTL) today:                         English/French (LTR) target:

┌──────────────────┬──────────────────┐    ┌──────────────────┬──────────────────┐
│   Stats sidebar  │  Bias narratives │    │  Bias narratives │   Stats sidebar  │
│                  │                  │    │                  │                  │
│  • Telegram      │  • مقایسه tab    │    │  • Comparison    │  • Telegram      │
│    analysis      │  • درون‌مرزی tab  │    │    tab           │    analysis      │
│  • Dispute       │  • برون‌مرزی tab  │    │  • Inside tab    │  • Dispute       │
│    score         │                  │    │  • Outside tab   │    score         │
│  • Silence       │  Articles list   │    │                  │  • Silence       │
│    detection     │  (filtered)      │    │  Articles list   │    detection     │
│  • Coordinated   │                  │    │                  │  • Coordinated   │
│    messaging     │                  │    │                  │    messaging     │
│  • Stats         │                  │    │                  │  • Stats         │
│  • Political     │                  │    │                  │  • Political     │
│    spectrum      │                  │    │                  │    spectrum      │
└──────────────────┴──────────────────┘    └──────────────────┴──────────────────┘
        left col            right col               left col            right col
        (second DOM child)  (first DOM child)       (first DOM child)   (second DOM child)
```

The DOM order stays the same. The browser swaps which column renders
on which side based on `<html dir>`. Tier 1 commit 1 just has to change
the physical padding/border classes on each column so the divider line
sits between them (not on an outer edge).

Specifically in the story detail page:

| Element | Today | Becomes |
|---|---|---|
| Narratives column wrapper | `lg:pl-6 lg:border-l` | `lg:ps-6 lg:border-s` |
| Stats sidebar wrapper | `lg:pr-6 lg:sticky lg:top-4` | `lg:pe-6 lg:sticky lg:top-4` |
| Coverage-bar max-width | `max-w-md` | unchanged — symmetric |
| Mobile-only StatsPanel | renders below narratives | unchanged — mobile is single-column |

#### Homepage hero — `app/[locale]/page.tsx`

```
Farsi (RTL) today:                         English/French (LTR) target:

┌────────────────────┬────────────────────┐    ┌────────────────────┬────────────────────┐
│ روایت برون‌مرزی   │  روایت درون‌مرزی   │    │ درون‌مرزی narrative│ برون‌مرزی narrative│
│ (outside/orange)   │  (inside/navy)     │    │  (inside/navy)     │  (outside/orange)  │
│                    │                    │    │                    │                    │
│ brief summary      │  brief summary     │    │  brief summary     │  brief summary     │
│ of what outside    │  of what inside    │    │  of what inside    │  of what outside   │
│ media said         │  media said        │    │  media said        │  media said        │
└────────────────────┴────────────────────┘    └────────────────────┴────────────────────┘
```

The inside/outside labels stay anchored to their color family
(navy=inside, orange=outside). What flips is which side renders first.

#### Homepage "most disputed" section

Each row: title on the outer edge, percentages on the inner edge. Same
grid-cols-2 pattern — flips automatically.

#### Mobile carousel layouts — `components/stories/*`

Six layouts (BlindspotLayout, MaxDisagreementLayout, TelegramLayout,
StoryLayout, StoryContentPanel, StoryBackground). On mobile RTL these
read right-to-left for the split screens. In LTR they should read
left-to-right. SplitScreen is the reusable base; fix it once, every
layout inherits.

#### Admin dashboard fetch-stats table — `app/[locale]/dashboard/fetch-stats/page.tsx`

This one is LTR already (admin tool), so no flip needed. But any
`text-right` for numeric columns should become `text-end` for
consistency.

**Files of concern** (from the prior audit — search these first):
- `frontend/src/app/[locale]/page.tsx` — homepage
- `frontend/src/app/[locale]/stories/[id]/page.tsx` — story detail
  (the telegram/stats sidebar swap lives here)
- `frontend/src/components/story/*`
- `frontend/src/components/home/*`
- `frontend/src/components/common/CoverageBar.tsx`, `BiasSpectrum.tsx`
- `frontend/src/components/source/PoliticalSpectrum.tsx`
- `frontend/src/components/layout/Header.tsx` — nav is commented out
  right now but will need logical classes when re-enabled
- `frontend/src/components/stories/*` — mobile carousel (BlindspotLayout,
  MaxDisagreementLayout, TelegramLayout, StoryContentPanel)

**Verification**: visit every page in Farsi; nothing should have moved.
Then manually set `dir="ltr"` on `<html>` via devtools and re-check —
layout should mirror correctly with no overlapping or broken visuals.

### Commit 2 — String extraction + en.json + fr.json (~4–6 hours)

1. Audit current messages: `frontend/src/messages/fa.json` is the
   existing file. Count existing keys, note gaps.
2. Extract every hardcoded Farsi string from JSX. Common targets:
   - `"بازگشت"`, `"بارگذاری"`, `"خطا"`, `"ببینید"`, etc.
   - Section titles like `"تحلیل روایت‌های تلگرام"`, `"زمینه خبر"`
   - Tab labels, button labels, tooltips
   - Placeholders, toast messages, error copy
   - Empty-state copy ("روایتی یافت نشد")
3. For each string, add a key (dot-path, e.g. `story.detail.noNarrative`)
   to all three message files:
   - `fa.json` — keep the existing Farsi string
   - `en.json` — human-written English
   - `fr.json` — AI-drafted French, flagged for human review
4. Replace JSX literals with `t("key")` calls using `useTranslations()`
   in client components and `getTranslations()` in server components.

**Rough string inventory** (from grep earlier): ~150–300 unique
Farsi literals across ~60 files. Conservative estimate: ~250 keys.

**Tooling**: I can run a grep-based extraction script that finds
Persian-script sequences in JSX and suggests a key name and where to
insert it. Human review needed for context-dependent phrasing.

**Content NOT to translate**:
- Proper nouns (BBC Persian, Tasnim, Iran International, Kayhan London).
- Source names (`name_en` / `name_fa` on Source model serve this).
- Telegram channel usernames.
- Persian vocabulary cues used in debug/admin views that reference the
  LLM prompt ("فتنه", "قیام" — these are data, not UI chrome).

### Commit 3 — Locale routing + switcher UI (~2 hours)

1. Register `en` and `fr` in the `next-intl` locales list (currently
   only `fa`). Likely in `src/i18n/config.ts` or `middleware.ts`.
2. Add a locale dropdown to `components/layout/Header.tsx`:
   - Small globe icon + current locale code
   - Menu with fa / en / fr
   - Clicking swaps the URL prefix (`/fa/...` ↔ `/en/...` ↔ `/fr/...`)
3. Update middleware to detect `Accept-Language` header for
   first-time visitors and redirect to the best match.
4. Ensure all internal `<Link>` components use `useLocale()` to build
   the locale-prefixed href (many already do; audit for hardcoded
   `/fa/` strings).

**Edge case**: existing deep links like `/fa/stories/xyz` continue to
work. A bare `/stories/xyz` (no locale) should 404 or redirect.

### Commit 4 — Polish pass (~2 hours)

1. **Persian numerals** — `lib/utils.ts::toFa()` converts Latin digits
   to Persian. Make it a no-op when `locale !== "fa"`:
   ```ts
   export function toFa(n: number, locale?: string): string {
     if (locale && locale !== "fa") return String(n);
     return /* existing conversion */;
   }
   ```
   Or pass `locale` through to every call site (prefer option 1).
2. **Date formatting** — `formatRelativeTime(iso, locale)` already
   accepts a locale. Verify Jalali (Farsi) vs Gregorian (EN/FR) paths.
3. **Fonts** — currently loads Vazirmatn + IBM Plex Sans. For EN/FR,
   Vazirmatn is unused. Load conditionally in `layout.tsx` to save a
   ~30KB font request.
4. **Empty-state copy** — add friendly EN/FR fallbacks for states
   like "no stories yet", "loading", "error".
5. **Accessibility** — every interactive element should have an
   `aria-label` that's also translated.

### Verification checklist (Tier 1)

- [ ] Load homepage in `/fa` — identical to today.
- [ ] Load homepage in `/en` — all chrome in English; layout mirrored
      (hero narrative cards swap, telegram sidebar on right).
- [ ] Load homepage in `/fr` — same as EN but in French.
- [ ] Story detail page — Telegram/stats sidebar flips from left to
      right. Bias tabs read LTR. Persian article titles still show
      (they're content, not chrome).
- [ ] Sources page, blindspots page, suggest page, rate page — same.
- [ ] Mobile carousel — if live, each layout (Blindspot, MaxDisagreement,
      Telegram) flips correctly. Swipe direction stays natural.
- [ ] Dashboard and admin pages — English-only is acceptable (internal
      tools); but if any Farsi strings leak in they should translate.
- [ ] Cold-load Lighthouse scores — should not regress.

---

## Tier 2 — Story content localization

**Scope**: story titles, summaries, bias explanations, editorial
context, per-subgroup narrative bullets — all emitted in fa + en + fr.

**Estimated effort**: ~30–60 hours + ongoing LLM cost increase.

### Approach: batch translation in the maintenance pipeline

The Niloofar editorial prompt + the story analysis prompt in
`backend/app/services/story_analysis.py` already emit `title_en` and
`summary_fa`. Extend them to also emit `title_fr` and `summary_fr`,
plus the localized versions of the subgroup bullet narrative we just
shipped in commit `bed087c`.

### DB schema

Three options ranked by cleanliness:

1. **Per-language columns on Story** — add `title_fr`, `summary_fr`,
   `bias_explanation_fr`, `editorial_context_fr`. Parallel to the
   existing `_en` columns. Simple but rigid — adding a new language
   later means a migration.
2. **JSONB map** — a single `title` JSONB column like
   `{"fa": "...", "en": "...", "fr": "..."}`. Flexible but every
   read needs a key lookup.
3. **Separate translation table** — `(story_id, locale, field, text)`.
   Overkill.

**Recommendation**: option 1. Matches existing pattern. One migration
per new language is fine.

### Prompt changes

`STORY_ANALYSIS_PROMPT` currently asks for Farsi bullets in
`narrative.{inside,outside}.{subgroup}`. Extend to:
```json
{
  "narrative_fa": { ... },
  "narrative_en": { ... },
  "narrative_fr": { ... }
}
```
With explicit instruction: "Bullets should be culturally fluent, not
direct translation. French version reads like a French journalist
wrote it."

### Cost impact

Per-story LLM output scales roughly linearly with languages. Current
output is ~600 tokens of Farsi bullets + summary. Adding EN + FR =
~1800 tokens output. At gpt-5-mini output pricing, that's roughly
**+$0.01 per story**. At 100 stories/day, **~$30/month extra**.

### Content NOT worth translating

- **Article body text** — user clicks through to the source anyway.
- **Telegram posts** — high volume, low payoff, often informal slang
  that doesn't translate well.
- **Source descriptions** — they're short, could be translated once
  and stored on the Source model (add `description_fr`).
- **Editorial context from Niloofar** — worth translating (low volume,
  high information density).

### Frontend changes for Tier 2

- Type definitions: `StoryDetail` gets `title_fr`, `summary_fr`, etc.
- Component-level: use `locale` to pick which `title_*` field to render.
- Fallback logic: if `title_fr` is null, show `title_en`; if that's
  null too, show `title_fa` with a subtle "(Farsi)" badge.

---

## Tier 3 — French-quality polish

**Scope**: professional review of the ~250 UI strings + a sample of
story summaries.

**Estimated effort**: ~1 day of native-speaker time. Parham's French
is native (Antibes, France) — feasibility depends on how much of your
own time you want to spend on it vs. a freelancer.

**What to check**:
- UI strings read naturally in context, not as word-for-word translation.
- Media-Persian idioms don't survive a literal translation — e.g.
  "روایت اپوزیسیون" as "opposition narrative" works in English but
  "récit de l'opposition" might need softening depending on tone.
- Labels on axes ("اصول‌گرا" = "principlist" in English; in French,
  "principaliste" is not a standard term — "conservateur" or
  "partisan de la ligne dure" may read better).

---

## Tricky details that will trip us up

### 1. Mixed-direction content in LTR mode

When an English user views a Farsi article title, it should render
RTL *within* the LTR page. HTML handles this if we wrap the Persian
text with `dir="rtl"` at the element level, but Tailwind's default
`text-start` on LTR containers will left-align the Persian text
(which is wrong — Persian still wants right alignment even inside an
LTR page).

**Fix**: create a `<Bidi>` component:
```tsx
<span dir={isPersian(text) ? "rtl" : "auto"} className={isPersian(text) ? "text-right" : ""}>{text}</span>
```
Used on any element that renders user-facing Persian inside a
potentially-LTR parent (story cards, search results, admin lists).

### 2. Persian vs Latin numerals in mixed UI

If an English user sees Iran's coverage percentages, they probably
want "34%" not "۳۴٪". Already handled by making `toFa()` locale-aware
(Tier 1 commit 4). But don't forget chart tooltips, table cells, and
the mobile carousel layouts.

### 3. Locale-aware collation

Sort-by-name on sources — Persian and English names collate
differently. `Intl.Collator(locale)` handles it. Low priority.

### 4. SEO and `hreflang`

Each story should have `<link rel="alternate" hreflang="en" href="..." />`
for its English and French versions. Next.js `generateMetadata` in
the route handles this via the `alternates` field.

### 5. LLM prompt for French

Vocabulary cues in `STORY_ANALYSIS_PROMPT` (`فتنه / قیام / سرکوب`)
are Farsi-specific. For a French-output run, replace with a French
media-vocabulary guide:
- Principlist: *islamiste, gardien de la révolution, résistance, ennemi sioniste*
- Reformist: *réformiste, société civile, droits des citoyens*
- Moderate diaspora: *régime iranien, manifestants, droits humains, observateurs*
- Radical diaspora: *régime des mollahs, répression, soulèvement, révolution*

Same structural prompt, different vocabulary section per output
language.

### 6. What about Arabic?

If you ever add Arabic, the good news is it's RTL like Farsi — the
same Tier 1 logical-CSS work applies. The bad news is numeric
formatting differs (Arabic-Indic digits ٠١٢٣٤٥٦٧٨٩ vs Farsi's
۰۱۲۳۴۵۶۷۸۹), and `hazm` (our Persian normalizer) doesn't handle
Arabic correctly. Plan Arabic support as its own Tier-2-equivalent
project, not as an afterthought.

---

## Phased recommendation

- **Now** (when you want to start): Tier 1 commits 1 + 2 + 3 ship
  chrome localization in ~1 day. Ship it behind a feature flag or
  just directly on `main`. Tier 1 commit 4 polish can happen the
  following day.
- **After 2 weeks of EN/FR traffic data**: decide whether Tier 2 is
  justified. If fewer than ~5% of sessions are English, don't bother
  with content translation.
- **If Tier 2 happens**: do Niloofar editorial context first (small
  LLM output, high value), then bias explanations, then titles.
- **Tier 3 polish**: any time, incremental.

## Files to update when this starts

Critical files for Tier 1 commit 1 (logical CSS):
- `frontend/src/app/[locale]/layout.tsx`
- `frontend/src/app/[locale]/page.tsx`
- `frontend/src/app/[locale]/stories/[id]/page.tsx`
- `frontend/src/components/common/CoverageBar.tsx`
- `frontend/src/components/common/BiasSpectrum.tsx`
- `frontend/src/components/story/*.tsx` (~10 files)
- `frontend/src/components/source/*.tsx` (~4 files)
- `frontend/src/components/home/*.tsx` (~6 files)
- `frontend/src/components/stories/*.tsx` (mobile carousel, ~6 files)
- `frontend/src/components/layout/Header.tsx`
- `frontend/src/messages/fa.json`

New files for Tier 1 commit 2:
- `frontend/src/messages/en.json`
- `frontend/src/messages/fr.json`
- Possibly `frontend/src/i18n/config.ts` if not already present.

Migration for Tier 2 (deferred):
- `backend/alembic/versions/NNNN_add_fr_columns.py` adding
  `title_fr`, `summary_fr`, `bias_explanation_fr`,
  `editorial_context_fr` to `stories` (JSONB where applicable).

## Risks to flag

- **Tier 1 risk**: the logical-CSS refactor is mechanical but large.
  Missing one `pr-*` → `pe-*` leaves a subtly-broken layout on LTR.
  Mitigation: after the refactor, load every page with `dir="ltr"`
  forced and screenshot-diff against RTL.
- **Tier 2 risk**: LLM cost scales with N languages. If French reader
  engagement is low, we've paid for translations that nobody reads.
  Mitigation: measure first, translate second.
- **Tier 3 risk**: AI-French is 85% fine; the 15% that's awkward can
  erode credibility with a French-speaking journalist audience. If
  you want French-speaking analysts to take the platform seriously,
  don't skip the native-speaker pass.

## Effort summary

| Tier | Time | Ongoing cost | Payoff |
|---|---|---|---|
| Tier 1 — chrome only | ~1–2 days | $0 | Reach EN/FR audiences; layout mirrored |
| Tier 2 — story content | ~1–2 weeks | ~$30/month LLM | Titles + summaries + bias in EN/FR |
| Tier 3 — French polish | ~1 day | $0 | Publishable quality for French journalists |

**Minimum viable version**: Tier 1, shippable in a week.
