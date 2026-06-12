// Unit tests for the homepage selection policy. Each block pins a rule
// that previously lived as untested inline logic in HomeBody.tsx —
// several of them encode hard-won editorial fixes (pinned hero, drought
// fallbacks, the «حضوری ندارد» meta-narrative gate), so a failure here
// means a policy regression, not a style issue.
import { describe, expect, it } from "vitest";
import type { StoryBrief } from "@/lib/types";
import {
  buildBattleItems,
  buildWordList,
  computeHomepagePicks,
  coverageBadgeContradicts,
  formatUpdateReason,
  hasTwoRealNarratives,
  isUpdateBadgeFresh,
  localizedStoryTitle,
  preferUnused,
  type AnalysesById,
  type StoryAnalysisBrief,
} from "./homepagePicks";

const NOW = Date.parse("2026-06-12T12:00:00Z");
const hoursAgo = (h: number) => new Date(NOW - h * 3600_000).toISOString();
const daysAgo = (d: number) => hoursAgo(d * 24);

let storySeq = 0;
function makeStory(overrides: Partial<StoryBrief> = {}): StoryBrief {
  storySeq += 1;
  return {
    id: overrides.id ?? `story-${storySeq}`,
    title_fa: `خبر شماره ${storySeq}`,
    title_en: `Story ${storySeq}`,
    slug: `story-${storySeq}`,
    article_count: 10,
    source_count: 5,
    covered_by_state: true,
    covered_by_diaspora: true,
    is_blindspot: false,
    blindspot_type: null,
    coverage_diversity_score: null,
    topics: [],
    first_published_at: daysAgo(1),
    last_updated_at: daysAgo(1),
    updated_at: daysAgo(1),
    state_pct: 50,
    diaspora_pct: 50,
    trending_score: 1,
    view_count: 0,
    image_url: "https://img.example/x.jpg",
    has_real_image: true,
    priority: 0,
    ...overrides,
  } as StoryBrief;
}

// ≥60 chars per side and no META pattern — passes hasTwoRealNarratives.
const LONG_STATE = "رسانه‌های درون‌مرزی این رویداد را به عنوان یک پیروزی بزرگ ملی و نشانه‌ای از اقتدار کشور توصیف کردند و بر ابعاد دفاعی آن تأکید داشتند.";
const LONG_DIASPORA = "رسانه‌های برون‌مرزی همین رویداد را نشانه‌ای از تشدید بحران و انزوای بین‌المللی دانستند و بر پیامدهای اقتصادی آن برای مردم تمرکز کردند.";

function makeAnalysis(overrides: Partial<StoryAnalysisBrief> = {}): StoryAnalysisBrief {
  return {
    state_summary_fa: LONG_STATE,
    diaspora_summary_fa: LONG_DIASPORA,
    bias_explanation_fa: "رسانه‌ها از واژه‌های «اقتدار» و «بحران» استفاده کردند.",
    loaded_words: { conservative: ["اقتدار"], opposition: ["بحران"] },
    ...overrides,
  };
}

function analysesFor(stories: StoryBrief[], a: Partial<StoryAnalysisBrief> = {}): AnalysesById {
  const out: AnalysesById = {};
  for (const s of stories) out[s.id] = makeAnalysis(a);
  return out;
}

function pick(stories: StoryBrief[], opts: {
  blindspots?: StoryBrief[];
  blindspotsAll?: StoryBrief[];
  analyses?: AnalysesById;
} = {}) {
  return computeHomepagePicks({
    stories,
    blindspots: opts.blindspots ?? [],
    blindspotsAll: opts.blindspotsAll ?? opts.blindspots ?? [],
    analyses: opts.analyses ?? analysesFor(stories),
    nowMs: NOW,
  });
}

describe("localizedStoryTitle", () => {
  const story = {
    title_fa: "عنوان فارسی",
    title_en: "English title",
    translations: { en: { title: "Voice-tuned EN title" } },
  };
  it("prefers the voice-tuned translation", () => {
    expect(localizedStoryTitle(story, "en")).toBe("Voice-tuned EN title");
  });
  it("falls back to flat title_en, then FA", () => {
    expect(localizedStoryTitle({ ...story, translations: undefined }, "en")).toBe("English title");
    expect(localizedStoryTitle({ title_fa: "عنوان فارسی" }, "en")).toBe("عنوان فارسی");
  });
  it("fa never reads translations", () => {
    expect(localizedStoryTitle(story, "fa")).toBe("عنوان فارسی");
  });
});

describe("buildWordList", () => {
  it("strips guillemets, dedupes, drops short words, sorts shortest-first, caps at 6", () => {
    const out = buildWordList(["«تجاوز»", "تجاوز", "ب", "حملهٔ گسترده", "جنگ", "تحریم", "اشغالگری", "مقاومت", "براندازی"]);
    expect(out).toHaveLength(6);
    expect(out[0]).toBe("جنگ"); // shortest first
    expect(out).toContain("تجاوز");
    expect(out.filter(w => w === "تجاوز")).toHaveLength(1); // deduped across «» strip
    expect(out).not.toContain("ب"); // < 3 chars dropped
  });
});

describe("preferUnused (cross-card word variety)", () => {
  it("leads with a word no prior card used, and records it", () => {
    const used = new Set<string>(["سرکوب"]);
    const out = preferUnused(["سرکوب", "حقوق بشر"], used);
    expect(out[0]).toBe("حقوق بشر");
    expect(used.has("حقوق بشر")).toBe(true);
  });
  it("keeps original order when every word is taken", () => {
    const used = new Set<string>(["سرکوب", "حقوق بشر"]);
    expect(preferUnused(["سرکوب", "حقوق بشر"], used)[0]).toBe("سرکوب");
  });
});

describe("hasTwoRealNarratives (تقابل gate)", () => {
  it("accepts two long real narratives", () => {
    expect(hasTwoRealNarratives(makeAnalysis())).toBe(true);
  });
  it("rejects short sides", () => {
    expect(hasTwoRealNarratives(makeAnalysis({ state_summary_fa: "کوتاه" }))).toBe(false);
  });
  it("rejects absence statements («حضوری ندارد» class, 2026-06-04 fix)", () => {
    const absence = "این زیرگروه در مجموعهٔ مقالات حاضر حضوری ندارد و روایت مستقلی از این رویداد ارائه نکرده است؛ بنابراین مقایسه ممکن نیست.";
    expect(hasTwoRealNarratives(makeAnalysis({ diaspora_summary_fa: absence }))).toBe(false);
  });
});

describe("update badge helpers", () => {
  it("orange badge expires after 24h (F5)", () => {
    const sig = { has_update: true, detected_at: hoursAgo(23) } as NonNullable<StoryBrief["update_signal"]>;
    expect(isUpdateBadgeFresh(sig, NOW)).toBe(true);
    expect(isUpdateBadgeFresh({ ...sig, detected_at: hoursAgo(25) }, NOW)).toBe(false);
  });
  it("legacy rows without detected_at render once", () => {
    expect(isUpdateBadgeFresh({ has_update: true } as any, NOW)).toBe(true);
    expect(isUpdateBadgeFresh({ has_update: false } as any, NOW)).toBe(false);
  });
  it("suppresses a coverage-began badge that contradicts the live split", () => {
    const story = makeStory({
      state_pct: 0,
      diaspora_pct: 100,
      update_signal: { has_update: true, kind: "coverage_shift", reason_fa: "پوشش درون‌مرزی آغاز شد", detected_at: hoursAgo(1) } as any,
    });
    expect(coverageBadgeContradicts(story)).toBe(true);
    // کمرنگ (weakened) is allowed to point at an empty side.
    const weakened = makeStory({
      state_pct: 0,
      diaspora_pct: 100,
      update_signal: { has_update: true, kind: "coverage_shift", reason_fa: "پوشش درون‌مرزی کمرنگ شد", detected_at: hoursAgo(1) } as any,
    });
    expect(coverageBadgeContradicts(weakened)).toBe(false);
  });
  it("stretches the burst window to real elapsed time", () => {
    const sig = { has_update: true, kind: "burst", new_count: 4, detected_at: hoursAgo(3), reason_fa: "۴ مقاله جدید در ساعت گذشته" } as any;
    expect(formatUpdateReason(sig, NOW)).toBe("۴ مقاله جدید در ۴ ساعت گذشته");
    // Fresh signal (≤30min) keeps the backend wording.
    expect(formatUpdateReason({ ...sig, detected_at: hoursAgo(0.2) }, NOW)).toBe("۴ مقاله جدید در ساعت گذشته");
  });
});

describe("computeHomepagePicks — hero", () => {
  it("a pinned story with narrative beats a higher-trending unpinned one", () => {
    const unpinned = makeStory({ id: "top" });
    const pinned = makeStory({ id: "pinned", priority: 10 });
    const { hero } = pick([unpinned, pinned]);
    expect(hero?.id).toBe("pinned");
  });
  it("pin requires freshness — a stale pin loses to a fresh narrative story", () => {
    const stalePinned = makeStory({ id: "stale-pin", priority: 10, last_updated_at: daysAgo(5), first_published_at: daysAgo(5) });
    const fresh = makeStory({ id: "fresh" });
    const { hero } = pick([stalePinned, fresh]);
    expect(hero?.id).toBe("fresh");
  });
  it("prefers a two-sided fresh story with narrative over one without narrative", () => {
    const noNarrative = makeStory({ id: "bare" });
    const withNarrative = makeStory({ id: "rich" });
    const analyses: AnalysesById = {
      bare: null,
      rich: makeAnalysis(),
    };
    const { hero } = pick([noNarrative, withNarrative], { analyses });
    expect(hero?.id).toBe("rich");
  });
  it("drought fallback: a 20d-old story still fills the slot when nothing fresher exists", () => {
    const old = makeStory({ id: "old", last_updated_at: daysAgo(20), first_published_at: daysAgo(20) });
    const { hero } = pick([old]);
    expect(hero?.id).toBe("old");
  });
  it("nothing beyond 26d is ever the hero", () => {
    const ancient = makeStory({ id: "ancient", last_updated_at: daysAgo(28), first_published_at: daysAgo(28) });
    const { hero } = pick([ancient]);
    expect(hero).toBeUndefined();
  });
});

describe("computeHomepagePicks — blindspots", () => {
  it("picks formal one-sided blindspots per side", () => {
    const stateOnly = makeStory({ id: "st", blindspot_type: "state_only", is_blindspot: true, state_pct: 90, diaspora_pct: 10 });
    const diasporaOnly = makeStory({ id: "di", blindspot_type: "diaspora_only", is_blindspot: true, state_pct: 5, diaspora_pct: 95 });
    const { conservativeBlind, oppositionBlind } = pick([], { blindspots: [stateOnly, diasporaOnly] });
    expect(conservativeBlind?.id).toBe("st");
    expect(oppositionBlind?.id).toBe("di");
  });
  it("a formal blindspot whose split flipped to balanced is rejected", () => {
    const flipped = makeStory({ id: "fl", blindspot_type: "state_only", is_blindspot: true, state_pct: 55, diaspora_pct: 45 });
    const { conservativeBlind } = pick([], { blindspots: [flipped] });
    expect(conservativeBlind).toBeUndefined();
  });
  it("falls back to a photo-less formal blindspot before the heuristic (2026-06-02 fix)", () => {
    const noPhoto = makeStory({ id: "np", blindspot_type: "diaspora_only", is_blindspot: true, state_pct: 0, diaspora_pct: 100, has_real_image: false });
    const { oppositionBlind } = pick([], { blindspots: [], blindspotsAll: [noPhoto] });
    expect(oppositionBlind?.id).toBe("np");
  });
  it("heuristic fallback uses the strict 80/20 gate on trending stories", () => {
    const oneSided = makeStory({ id: "h", state_pct: 85, diaspora_pct: 15 });
    const balanced = makeStory({ id: "b", state_pct: 75, diaspora_pct: 25 });
    const { conservativeBlind } = pick([oneSided, balanced]);
    expect(conservativeBlind?.id).toBe("h");
  });
  it("never shows a blindspot older than 7d", () => {
    const old = makeStory({ id: "old", blindspot_type: "state_only", is_blindspot: true, state_pct: 95, diaspora_pct: 5, last_updated_at: daysAgo(9), first_published_at: daysAgo(9) });
    const { conservativeBlind } = pick([], { blindspots: [old] });
    expect(conservativeBlind).toBeUndefined();
  });
});

describe("computeHomepagePicks — no story appears in two slots", () => {
  it("hero, battle, briefing and most-viewed are disjoint", () => {
    const stories = Array.from({ length: 12 }, (_, i) =>
      makeStory({ id: `s${i}`, state_pct: 40 + i, diaspora_pct: 60 - i, view_count: i }));
    const picks = pick(stories);
    const ids = [
      picks.hero?.id,
      ...picks.battleReserved.map(s => s.id),
      ...picks.leftTextStories.map(s => s.id),
      ...picks.mostViewed.map(s => s.id),
    ].filter(Boolean) as string[];
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe("computeHomepagePicks — تقابل reservation", () => {
  it("reserves up to 4 two-sided stories sorted by coverage spread", () => {
    // 78/22 stays under the 80/20 heuristic-blindspot gate so the battle
    // box (not the نگاه یک‌جانبه slot) gets the widest-spread story.
    const stories = [
      makeStory({ id: "near", state_pct: 52, diaspora_pct: 48 }),
      makeStory({ id: "wide", state_pct: 78, diaspora_pct: 22 }),
      makeStory({ id: "mid", state_pct: 65, diaspora_pct: 35 }),
      makeStory({ id: "hero-eater" }), // consumed by hero slot first
    ];
    const { battleReserved, hero } = pick(stories);
    expect(hero?.id).toBe("near"); // first two-sided fresh story wins hero
    expect(battleReserved.map(s => s.id)).toEqual(["wide", "mid", "hero-eater"]);
  });
  it("excludes blindspot-flagged and one-sided stories", () => {
    const stories = [
      makeStory({ id: "ok", state_pct: 60, diaspora_pct: 40 }),
      makeStory({ id: "flagged", is_blindspot: true, state_pct: 60, diaspora_pct: 40 }),
      makeStory({ id: "one-sided", state_pct: 100, diaspora_pct: 0 }),
    ];
    const { battleReserved } = pick(stories);
    const ids = battleReserved.map(s => s.id);
    expect(ids).not.toContain("flagged");
    expect(ids).not.toContain("one-sided");
  });
  it("stories whose narratives are absence statements never reach the box", () => {
    const stories = [makeStory({ id: "a" }), makeStory({ id: "b" })];
    const absence = "این زیرگروه در مجموعهٔ مقالات حاضر حضوری ندارد و روایت مستقلی از این رویداد ارائه نکرده است؛ بنابراین مقایسه ممکن نیست.";
    const analyses = analysesFor(stories, { diaspora_summary_fa: absence });
    const { battleReserved } = pick(stories, { analyses });
    expect(battleReserved).toHaveLength(0);
  });
});

describe("computeHomepagePicks — پرمخاطب‌ترین", () => {
  it("ranks by the popularity score (views dominate) and caps at 3", () => {
    // Upstream slots drain the pool first: hero takes hero-slot, the
    // heuristic blindspot takes one 100/0 story, the briefing strip
    // takes the next three. The most-viewed box then ranks what's left
    // — so the viral story must NOT be the blindspot/briefing pick to
    // reach this box. One-sided stories keep the battle box empty.
    const stories = [
      makeStory({ id: "hero-slot" }),
      makeStory({ id: "blind-eater", state_pct: 100, diaspora_pct: 0 }),
      makeStory({ id: "brief1", state_pct: 100, diaspora_pct: 0 }),
      makeStory({ id: "brief2", state_pct: 100, diaspora_pct: 0 }),
      makeStory({ id: "brief3", state_pct: 100, diaspora_pct: 0 }),
      makeStory({ id: "quiet", view_count: 1, state_pct: 100, diaspora_pct: 0 }),
      makeStory({ id: "viral", view_count: 100, state_pct: 100, diaspora_pct: 0 }),
      makeStory({ id: "mid", view_count: 10, state_pct: 100, diaspora_pct: 0 }),
    ];
    const { mostViewed, leftTextStories } = pick(stories);
    expect(leftTextStories.map(s => s.id)).toEqual(["brief1", "brief2", "brief3"]);
    expect(mostViewed.map(s => s.id)).toEqual(["viral", "mid", "quiet"]);
    expect(mostViewed[0]._popScore).toBeGreaterThan(mostViewed[2]._popScore);
  });
});

describe("buildBattleItems", () => {
  it("builds cards with word lists from loaded_words", () => {
    const stories = [makeStory({ id: "x" })];
    const items = buildBattleItems(stories, analysesFor(stories), "fa");
    expect(items).toHaveLength(1);
    expect(items[0].conservativeWords).toEqual(["اقتدار"]);
    expect(items[0].stateSummary).toBe(LONG_STATE);
  });
  it("falls back to «»-quoted bias text split across sides", () => {
    const stories = [makeStory({ id: "q" })];
    const analyses: AnalysesById = {
      q: makeAnalysis({
        loaded_words: undefined,
        bias_explanation_fa: "یک سو از «پیروزی قاطع» گفت و سوی دیگر از «شکست سنگین» نوشت.",
      }),
    };
    const items = buildBattleItems(stories, analyses, "fa");
    expect(items).toHaveLength(1);
    expect(items[0].conservativeWords).toEqual(["پیروزی قاطع"]);
    expect(items[0].oppositionWords).toEqual(["شکست سنگین"]);
  });
  it("diversifies the leading word across cards", () => {
    const stories = [makeStory({ id: "c1" }), makeStory({ id: "c2" })];
    const shared = { conservative: ["اقتدار", "امنیت ملی"], opposition: ["سرکوب", "حقوق بشر"] };
    const analyses = analysesFor(stories, { loaded_words: shared });
    const items = buildBattleItems(stories, analyses, "fa");
    expect(items[0].oppositionWords[0]).toBe("سرکوب");
    expect(items[1].oppositionWords[0]).toBe("حقوق بشر");
  });
});
