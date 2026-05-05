"use client";

// /dashboard/engineering — Engineering invariants reference. For a
// future maintainer who didn't live through the incidents that
// produced each guard rail. Static page — no fetches, no live data.
//
// The 351-test suite encodes ~8 months of incident learnings. This
// page is the "why does this exist" companion to the test files.
// Keep this in sync if you add or remove a test file in
// backend/tests/.

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  ShieldCheck,
  AlertTriangle,
  FileCode,
  GitBranch,
  Cpu,
  Network,
  Search,
  ScrollText,
  DollarSign,
} from "lucide-react";

type TestFile = {
  id: string;
  filename: string;
  testCount: number;
  icon: React.ReactNode;
  color: string;
  pins: string;
  exampleInvariants: string[];
  incidentsCovered: string[];
};

const TEST_FILES: TestFile[] = [
  {
    id: "war-audit",
    filename: "test_war_audit_fixes.py",
    testCount: 22,
    icon: <ShieldCheck className="h-5 w-5" />,
    color: "border-red-500 bg-red-50 dark:bg-red-900/10",
    pins: "Specific bug classes from the 2026-05-03 war-mode session.",
    exampleInvariants: [
      "Embedding wrappers return None on failure (no zero-vector silent fallback)",
      "processed_at not set when embedding failed (sentinel-trap defense)",
      "Frozen stories STAY on homepage (filtered by priority, not removed)",
      "GPT-5 family uses JSON mode + 2x token budget for reasoning headroom",
      "Pinned stories (priority > 0) skip auto-freeze + auto-demote",
    ],
    incidentsCovered: [
      "1097 articles permanently orphaned by the processed_at sentinel bug",
      "Hero card disappeared when frozen-stays-visible rule was violated",
      "9/10 gpt-5 story_analysis JSON parses failed with old token budget",
    ],
  },
  {
    id: "clustering",
    filename: "test_clustering_safety.py",
    testCount: 18,
    icon: <Network className="h-5 w-5" />,
    color: "border-purple-500 bg-purple-50 dark:bg-purple-900/10",
    pins: "Clustering matcher + homepage_scope contract.",
    exampleInvariants: [
      "Threshold ladder strictly increases: 0.40 (fresh) < 0.55 (aged) < 0.65 (near-freeze)",
      "Matcher SELECT excludes frozen, archived, max-size, 7d-umbrella stories",
      "step_recluster_orphans applies the same gates as the matcher",
      "Small target stories (article_count < 10) require signal overlap",
      "Trending excludes archived but NOT frozen (Parham 2026-05-03 rule)",
    ],
    incidentsCovered: [
      "5adc903e Brazil-protest cluster grew to 30 unrelated articles over 24 days",
      "Iran-UAE umbrella drift caught by title cohesion gate",
      "Empty homepage incident when freeze rule got too aggressive",
    ],
  },
  {
    id: "freshness",
    filename: "test_story_freshness.py",
    testCount: 27,
    icon: <ScrollText className="h-5 w-5" />,
    color: "border-orange-500 bg-orange-50 dark:bg-orange-900/10",
    pins: "Update-signal logic that drives the orange/green badge.",
    exampleInvariants: [
      "Dispute / coverage / new-articles thresholds + precedence",
      "Dispute reason has NO digits (post-2026-05-05 readability change)",
      "Coverage 0-edge phrasing uses آغاز شد / کمرنگ شد without parenthetical",
      "Persian digits required, Latin digits forbidden in display strings",
      "Snapshot text fields cap at 2000 chars (JSONB row size)",
    ],
    incidentsCovered: [
      "Reader confusion over abstract dispute_score numbers (1.0 ← 0.6)",
      "Misleading 0% historical baselines on coverage shifts",
    ],
  },
  {
    id: "api-contracts",
    filename: "test_api_contracts.py",
    testCount: 19,
    icon: <FileCode className="h-5 w-5" />,
    color: "border-blue-500 bg-blue-50 dark:bg-blue-900/10",
    pins: "Pydantic schema + endpoint response_model wiring.",
    exampleInvariants: [
      "StoryBrief required fields the frontend reads by name",
      "image_url and update_signal stay Optional (None-allowed)",
      "priority defaults to 0 (pin protection logic depends on this)",
      "/trending and /blindspots return list[StoryBrief]",
      "bias_scoring routes through homepage_scope.homepage_story_ids",
    ],
    incidentsCovered: [
      "April-May 2026 cost overruns from spend gates drifting from API filters",
      "Hero card crash when image_url type was tightened to non-optional",
    ],
  },
  {
    id: "story-analysis",
    filename: "test_story_analysis_parsing.py",
    testCount: 22,
    icon: <Cpu className="h-5 w-5" />,
    color: "border-indigo-500 bg-indigo-50 dark:bg-indigo-900/10",
    pins: "LLM JSON output parsing + defaults + fallback flatten.",
    exampleInvariants: [
      "Code-fence stripping (```json and bare ```)",
      "Invalid JSON raises RuntimeError (no silent default-fill)",
      "All 14 required keys default-filled when LLM omits them",
      "Bullet flatten fills legacy fields without overwriting explicit values",
      "Quote-pair counter uses min(open, close) — defeats spam-spike",
    ],
    incidentsCovered: [
      "Truncated GPT-5 JSON responses (silently empty stories)",
      "LLM emitted invented framing labels — broke bar chart styling",
    ],
  },
  {
    id: "telegram",
    filename: "test_telegram_analysis.py",
    testCount: 19,
    icon: <Network className="h-5 w-5" />,
    color: "border-cyan-500 bg-cyan-50 dark:bg-cyan-900/10",
    pins: "Channel-name canonicalization + link/reassign thresholds.",
    exampleInvariants: [
      "_normalize_channel_name strips @, «», 'کانال' prefix, folds Arabic ي→ی",
      "Telegram link threshold 0.35 + 0.10 aged bump = 0.45 (mirrors article 0.40→0.55)",
      "Reassign min_score stricter than link threshold (no thrash)",
      "_clean_vec defends both link + reassign against legacy dict centroids",
    ],
    incidentsCovered: [
      "0% supporter coverage on every prediction when normalization regressed",
      "Posts thrashed between similar stories every cron tick when drift_gap was too low",
    ],
  },
  {
    id: "pipeline",
    filename: "test_pipeline_shape.py",
    testCount: 22,
    icon: <GitBranch className="h-5 w-5" />,
    color: "border-emerald-500 bg-emerald-50 dark:bg-emerald-900/10",
    pins: "Maintenance pipeline ordering + dispatch resolution.",
    exampleInvariants: [
      "Every step name in FULL_PIPELINE / INGEST_ONLY_PIPELINE has an async function",
      "Critical orderings: process → cluster → centroids → recluster → summarize",
      "telegram_reassign + HOURLY_PIPELINE stay removed (chronic timeouts)",
      "FULL_PIPELINE pinned at 56 steps; INGEST_ONLY at 13 (dashboard progress bar)",
      "Both pipelines start with `ingest`",
    ],
    incidentsCovered: [
      "telegram_reassign 1215s timeout on every full run for weeks",
      "Leftover hourly cron firing every 21 min, leaving ghost locks",
      "Stale-data bugs from running steps in the wrong order",
    ],
  },
  {
    id: "ingestion",
    filename: "test_ingestion_helpers.py",
    testCount: 36,
    icon: <Search className="h-5 w-5" />,
    color: "border-amber-500 bg-amber-50 dark:bg-amber-900/10",
    pins: "RSS / image / language helpers at the front door.",
    exampleInvariants: [
      "_is_icon_like rejects favicons, apple-touch, pwa-icons before DB write",
      "_extract_image_from_html rejects relative URLs, data: URIs, tiny images, logos",
      "_extract_rss_category handles list-of-dicts AND string forms",
      "parse_published_date prefers published over updated, returns tz-aware",
      "detect_language folds Arabic to fa, defaults fa on detection failure",
    ],
    incidentsCovered: [
      "Logos showing as story cover images on the homepage",
      "Stories ingested with relative-URL image_url — broke when proxied",
    ],
  },
  {
    id: "events",
    filename: "test_events.py",
    testCount: 14,
    icon: <ScrollText className="h-5 w-5" />,
    color: "border-pink-500 bg-pink-50 dark:bg-pink-900/10",
    pins: "Audit-log writer's SAVEPOINT semantics + parameterized SQL.",
    exampleInvariants: [
      "log_event swallows DB errors — never blocks the caller's transaction",
      "INSERT wrapped in db.begin_nested() (SAVEPOINT) for tx isolation",
      "All values via :bound parameters (no f-string SQL)",
      "Default actor='pipeline', commit=False",
      "_clip truncates at 2000 chars + ellipsis",
    ],
    incidentsCovered: [
      "greenlet_spawn errors mid-loop when log_event poisoned the outer tx",
    ],
  },
  {
    id: "bias-parsing",
    filename: "test_bias_scoring_parsing.py",
    testCount: 21,
    icon: <Cpu className="h-5 w-5" />,
    color: "border-rose-500 bg-rose-50 dark:bg-rose-900/10",
    pins: "Bias-LLM JSON parser + score clamping + framing whitelist.",
    exampleInvariants: [
      "Returns None (not raise) on JSON failure — caller treats as 'skip'",
      "Signed scores clamped to [-1, 1]; unsigned to [0, 1]",
      "framing_labels filtered against FRAMING_LABELS whitelist",
      "_estimate_confidence: 4-field × 0.85 + 0.10 reasoning + 0.05 framing, capped at 1.0",
    ],
    incidentsCovered: [
      "LLM occasionally returned out-of-range scores breaking visual scaling",
      "Invented framing labels rendered as unstyled chips",
    ],
  },
  {
    id: "pricing",
    filename: "test_llm_pricing.py",
    testCount: 22,
    icon: <DollarSign className="h-5 w-5" />,
    color: "border-yellow-500 bg-yellow-50 dark:bg-yellow-900/10",
    pins: "OpenAI cost calculator math.",
    exampleInvariants: [
      "Snapshot models resolve to base via longest-prefix (gpt-4o-mini-2024-07-18 → gpt-4o-mini)",
      "cached_input_tokens is a SUBSET of input_tokens (no double-counting)",
      "Cached tokens capped at input total (defensive)",
      "Pro models with no cached rate charge cached at input rate",
      "Unknown models return $0 with rate_source=None (logged for follow-up)",
    ],
    incidentsCovered: [
      "Cost dashboard showed $0/day when snapshot models slipped through pricing",
    ],
  },
];

const TOTAL_TESTS = TEST_FILES.reduce((acc, f) => acc + f.testCount, 0);

function TestFileCard({
  file,
  isExpanded,
  onToggle,
}: {
  file: TestFile;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className={`border ${file.color} p-5`}>
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between text-left"
      >
        <div className="flex items-center gap-3">
          <div className="text-slate-700 dark:text-slate-300">{file.icon}</div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-white font-mono">
              {file.filename}
            </h3>
            <p className="text-xs text-slate-500">
              {file.testCount} tests — {file.pins}
            </p>
          </div>
        </div>
        {isExpanded ? (
          <ChevronUp className="h-4 w-4 text-slate-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-slate-400" />
        )}
      </button>

      {isExpanded && (
        <div className="mt-4 space-y-4">
          <div>
            <h4 className="text-xs font-bold text-slate-700 dark:text-slate-300 mb-2">
              Example invariants pinned
            </h4>
            <ul className="space-y-1">
              {file.exampleInvariants.map((inv, i) => (
                <li
                  key={i}
                  className="text-xs text-slate-600 dark:text-slate-400 flex items-start gap-2"
                >
                  <span className="text-slate-400 mt-0.5">•</span>
                  <span>{inv}</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h4 className="text-xs font-bold text-slate-700 dark:text-slate-300 mb-2">
              Past incidents this would have caught
            </h4>
            <ul className="space-y-1">
              {file.incidentsCovered.map((inc, i) => (
                <li
                  key={i}
                  className="text-xs text-slate-500 flex items-start gap-2"
                >
                  <span className="text-slate-400 mt-0.5">→</span>
                  <span>{inc}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

export default function EngineeringPage() {
  const [authed, setAuthed] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (
      typeof window !== "undefined" &&
      localStorage.getItem("doornegar_admin_token")
    ) {
      setAuthed(true);
    }
  }, []);

  if (!authed) {
    return (
      <div className="mx-auto max-w-sm px-4 py-24 text-center">
        <p className="text-slate-500">
          Access the{" "}
          <Link href="./." className="text-blue-600 hover:underline">
            dashboard
          </Link>{" "}
          first to authenticate.
        </p>
      </div>
    );
  }

  const toggleAll = () => {
    if (expanded.size === TEST_FILES.length) {
      setExpanded(new Set());
    } else {
      setExpanded(new Set(TEST_FILES.map((f) => f.id)));
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <Link
              href="./."
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
            >
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
              Engineering Invariants
            </h1>
          </div>
          <p className="text-sm text-slate-500">
            For the engineer who didn&apos;t live through the incidents that
            produced each guard rail. Keep this in sync with{" "}
            <code className="font-mono text-[11px]">backend/tests/</code>.
          </p>
        </div>
        <button
          onClick={toggleAll}
          className="text-xs border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800"
        >
          {expanded.size === TEST_FILES.length ? "Collapse All" : "Expand All"}
        </button>
      </div>

      {/* Philosophy banner */}
      <div className="mb-8 border border-slate-200 dark:border-slate-800 p-5 bg-slate-50 dark:bg-slate-900/40">
        <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-3">
          The test suite is a tripwire grid, not documentation
        </h2>
        <div className="text-sm text-slate-600 dark:text-slate-400 space-y-2">
          <p>
            Doornegar has{" "}
            <strong className="text-slate-900 dark:text-white">
              {TOTAL_TESTS} tests
            </strong>{" "}
            across {TEST_FILES.length} files. Each test maps 1:1 to either a
            past incident or an invariant whose violation would break the
            homepage. <strong>Don&apos;t read the tests; the tests read your
            code for you.</strong>
          </p>
          <p>
            CI runs <code className="font-mono text-[11px]">pytest tests/ -q</code>{" "}
            on every push to <code>main</code> and every PR
            (<code className="font-mono text-[11px]">.github/workflows/ci.yml</code>).
            The full suite finishes in under 1 second — fast enough that nobody
            has an excuse to skip it.
          </p>
        </div>
      </div>

      {/* Three loops */}
      <div className="mb-8 grid gap-4 sm:grid-cols-3">
        <LoopCard
          n={1}
          title="Pre-merge"
          body="CI runs the suite on every PR. If you broke a guard rail, you see it before merge. The test message names the bug class — you don't need to remember the original incident."
        />
        <LoopCard
          n={2}
          title="When something fails"
          body="A failing test is a structured incident report: name = which guard rail tripped, message = why it exists, file = which subsystem you're touching. Don't change the test to make it pass — read the message, fix the code."
        />
        <LoopCard
          n={3}
          title="Periodic audit"
          body="Every few months, run pytest --collect-only and read the test names like a table of contents. Modules with no tests are blind spots. Recent incidents with no test slipped past — add the regression net retroactively."
        />
      </div>

      {/* When a test fails */}
      <div className="mb-8 border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/10 p-5">
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="space-y-2">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              When a test fails
            </h3>
            <ol className="text-sm text-slate-700 dark:text-slate-300 space-y-1 list-decimal list-inside">
              <li>
                Read the assertion message — it names the original incident or
                the rule being pinned.
              </li>
              <li>
                Look at the test docstring and the code it&apos;s checking. The
                test usually links to a memory file or commit.
              </li>
              <li>
                <strong>If your code is wrong</strong>: fix the code, not the
                test.
              </li>
              <li>
                <strong>If the rule should genuinely change</strong>: update
                the test AND the related memory file in the same PR. Add a
                note in the commit explaining why the invariant is no longer
                load-bearing.
              </li>
            </ol>
          </div>
        </div>
      </div>

      {/* After a new incident */}
      <div className="mb-8 border border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/10 p-5">
        <div className="flex items-start gap-3">
          <ShieldCheck className="h-5 w-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
          <div className="space-y-2">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              After fixing a new incident, add ONE test
            </h3>
            <p className="text-sm text-slate-700 dark:text-slate-300">
              Even a source-inspection test (
              <code className="font-mono text-[11px]">
                assert &quot;X&quot; in src
              </code>
              ) is enough. The memory of the incident fades; the test
              doesn&apos;t. Add it to an existing file if the bug class fits,
              or create a new one. Each test should name what it tripwires
              and (if applicable) reference the memory file or commit that
              documents the original incident.
            </p>
          </div>
        </div>
      </div>

      {/* Test file grid */}
      <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-4">
        Test files — what each pins
      </h2>
      <div className="grid gap-4 sm:grid-cols-2">
        {TEST_FILES.map((file) => (
          <TestFileCard
            key={file.id}
            file={file}
            isExpanded={expanded.has(file.id)}
            onToggle={() => {
              const next = new Set(expanded);
              if (next.has(file.id)) next.delete(file.id);
              else next.add(file.id);
              setExpanded(next);
            }}
          />
        ))}
      </div>

      {/* What's NOT tested */}
      <div className="mt-8 border border-slate-200 dark:border-slate-800 p-5">
        <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-3">
          What deliberately isn&apos;t tested (yet)
        </h3>
        <p className="text-sm text-slate-600 dark:text-slate-400 mb-3">
          The test suite is a map of what has hurt before. These modules
          haven&apos;t produced a homepage outage, so they&apos;re uncovered —
          add tests retroactively when an incident reveals a new bug class:
        </p>
        <ul className="text-xs text-slate-500 space-y-1 list-disc list-inside font-mono">
          <li>app/services/story_ops.py (HITL split/scaffold/find primitives)</li>
          <li>app/services/scraper.py (article-page text extraction)</li>
          <li>app/services/social_posting.py</li>
          <li>app/services/rating_aggregation.py</li>
          <li>nlp_pipeline beyond the processed_at trap</li>
        </ul>
      </div>
    </div>
  );
}

function LoopCard({
  n,
  title,
  body,
}: {
  n: number;
  title: string;
  body: string;
}) {
  return (
    <div className="border border-slate-200 dark:border-slate-800 p-4">
      <div className="text-xs text-slate-400 mb-1">Loop {n}</div>
      <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-2">
        {title}
      </h3>
      <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
        {body}
      </p>
    </div>
  );
}
