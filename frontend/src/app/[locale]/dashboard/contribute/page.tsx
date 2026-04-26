import Link from "next/link";

// Big-picture map of every contribution path available on Doornegar.
// Lives at /dashboard/contribute. Reference page only — no fetches,
// no client interactivity. Update this when a new entry point ships
// so raters and admins always have a single overview.

export const metadata = {
  title: "Contributor map",
};

type Entry = {
  label: string;
  href?: string;
  description: string;
  audience: "anyone" | "rater" | "admin";
  surface: string;
  effect: string;
};

const ENTRIES: { group: string; items: Entry[] }[] = [
  {
    group: "Public — anyone with the link",
    items: [
      {
        label: "Rate the homepage",
        href: "/fa/rate",
        description:
          "Mirror of the homepage with feedback overlays on every story card. Flag wrong title, suggest a better image, push priority up/down, propose a merge.",
        audience: "anyone",
        surface: "/fa/rate",
        effect:
          "Submits anonymous improvement_feedback rows. 3 distinct fingerprints on the same target → orphan-and-rehome at the next cron tick.",
      },
      {
        label: "Per-story feedback overlay",
        href: "/fa/stories",
        description:
          "Open any story with `?feedback=1` (or click through from /rate) to get a floating sidebar with 8 targets: title, image, summary, clustering, articles, source class, source dimensions, layout.",
        audience: "anyone",
        surface: "/fa/stories/{id}?feedback=1",
        effect:
          "Same improvement_feedback table; targetType is set per button so admins can filter by category in /dashboard/improvements.",
      },
      {
        label: "Mark an article unrelated",
        description:
          "On the story page, every article in the stacked list has its own «نامرتبط» button next to the source link.",
        audience: "anyone",
        surface: "/fa/stories/{id} — per-article control",
        effect:
          "Records a hard-negative (article, story) pair. Clustering refuses to re-attach that article to that story for 90 days.",
      },
      {
        label: "Submit a story we missed",
        href: "/fa/submit",
        description:
          "Paste a URL or paste the article text. Optionally link to an existing story; otherwise Niloofar attaches it.",
        audience: "anyone",
        surface: "/fa/submit",
        effect:
          "POST /api/v1/improvements (target=story). Queued for HITL review at /dashboard/review-queue.",
      },
      {
        label: "Suggest a new source",
        href: "/fa/suggest",
        description:
          "Propose a media outlet to add — name, RSS URL, suggested classification.",
        audience: "anyone",
        surface: "/fa/suggest",
        effect:
          "Saved as source_suggestion. Reviewed manually; once approved, a follow-up ingest run pulls its RSS feed.",
      },
      {
        label: "Public feedback button",
        description:
          "Floating bottom-right button on every story page for free-form feedback when none of the targeted controls fit.",
        audience: "anyone",
        surface: "/fa/stories/{id} — PublicFeedbackButton",
        effect:
          "Generic improvement_feedback row with target=story and free-text reason.",
      },
      {
        label: "Blindspots feed",
        href: "/fa/blindspots",
        description:
          "Browse stories that are covered by only one side. No direct submission UI, but the rate-overlay buttons work here too.",
        audience: "anyone",
        surface: "/fa/blindspots",
        effect: "Read-only.",
      },
    ],
  },
  {
    group: "Trusted raters — token in localStorage",
    items: [
      {
        label: "Rater feedback (single-vote action)",
        description:
          "Same overlay buttons as anyone, but each submission is tagged with the rater's token. One vote is enough to act (anonymous needs 3 fingerprints).",
        audience: "rater",
        surface: "/fa/rate or /fa/stories/{id}?feedback=1",
        effect:
          "Writes to rater_feedback. Maintenance-cron applies the action immediately (rename, image swap, orphan, regen).",
      },
      {
        label: "Editable title",
        description:
          "Click the story title on any story page to inline-edit it. Token holders only.",
        audience: "rater",
        surface: "/fa/stories/{id} — EditableTitle",
        effect:
          "Direct rater_feedback row; cron applies the rename after one vote.",
      },
      {
        label: "Priority control",
        description:
          "Up/down arrows under the story title (rater-only) push trending priority.",
        audience: "rater",
        surface: "/fa/stories/{id} — PriorityControl",
        effect: "Adjusts trending_score; reflected on the next cron tick.",
      },
      {
        label: "Niloofar audit",
        description:
          "Niloofar (Claude persona) reviews wrong_clustering submissions and tags them agree / disagree / ambiguous. Source trust score adjusts based on her verdicts plus 30-day flag rate.",
        audience: "rater",
        surface: "/dashboard/learning — Source trust tab",
        effect:
          "Daily recompute. Sources with sustained high flag rates get cluster_quality_score < 1.0, which scales their cosine threshold up so they cluster more cautiously.",
      },
    ],
  },
  {
    group: "Admin / HITL — internal-only",
    items: [
      {
        label: "Review queue",
        href: "/fa/dashboard/review-queue",
        description:
          "Triage incoming improvement_feedback and rater_feedback that the cron didn't auto-apply.",
        audience: "admin",
        surface: "/fa/dashboard/review-queue",
        effect: "Manual accept/reject; writes to feedback_decisions.",
      },
      {
        label: "HITL surfaces",
        href: "/fa/dashboard/hitl",
        description:
          "Source classification, story scaffolding, image assignment, story splits.",
        audience: "admin",
        surface: "/fa/dashboard/hitl/*",
        effect: "Direct DB writes via story_ops endpoints.",
      },
      {
        label: "Story editor",
        href: "/fa/dashboard/edit-stories",
        description:
          "Bulk merge, split, delete stories. Used to clean up clustering errors that the auto-pipeline missed.",
        audience: "admin",
        surface: "/fa/dashboard/edit-stories",
        effect: "Triggers re-cluster + metadata refresh.",
      },
      {
        label: "Feedback inbox",
        href: "/fa/dashboard/improvements",
        description:
          "All improvement_feedback + suggestion rows. Filterable by target type and status.",
        audience: "admin",
        surface: "/fa/dashboard/improvements",
        effect: "Read + status updates.",
      },
      {
        label: "Learning dashboard",
        href: "/fa/dashboard/learning",
        description:
          "Two tabs: events feed (orphan/rehome/summary-regen/cluster-block events emitted by cron), and the per-source trust table.",
        audience: "admin",
        surface: "/fa/dashboard/learning",
        effect: "Read-only telemetry.",
      },
      {
        label: "Manual maintenance trigger",
        description:
          "POST /api/v1/admin/maintenance/run with the bearer token to fire the full pipeline outside the 04:00 UTC cron.",
        audience: "admin",
        surface: "API (curl + ADMIN_TOKEN)",
        effect: "Runs FULL_PIPELINE end-to-end.",
      },
    ],
  },
];

const AUDIENCE_BADGE: Record<Entry["audience"], string> = {
  anyone:
    "border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300",
  rater:
    "border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-950/30 text-blue-700 dark:text-blue-300",
  admin:
    "border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-300",
};

const AUDIENCE_LABEL: Record<Entry["audience"], string> = {
  anyone: "public",
  rater: "rater",
  admin: "admin",
};

export default function ContributePage() {
  return (
    <div dir="ltr" className="max-w-5xl mx-auto px-4 py-8">
      <header className="mb-8 pb-6 border-b border-slate-200 dark:border-slate-800">
        <h1 className="text-2xl font-black text-slate-900 dark:text-white">
          Contributor map
        </h1>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400 max-w-2xl">
          Every place a user can send signal into Doornegar — public entry
          points, trusted-rater actions, and admin surfaces — with what
          each one writes and what the system does with it.
        </p>
      </header>

      {ENTRIES.map((group) => (
        <section key={group.group} className="mb-10">
          <h2 className="text-sm font-black uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-4">
            {group.group}
          </h2>
          <div className="border border-slate-200 dark:border-slate-800 divide-y divide-slate-200 dark:divide-slate-800">
            {group.items.map((entry) => (
              <article key={entry.label} className="p-4 grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3 md:gap-6">
                <div>
                  <div className="flex items-center gap-2 mb-1.5">
                    <h3 className="text-[15px] font-bold text-slate-900 dark:text-white">
                      {entry.href ? (
                        <Link
                          href={entry.href}
                          className="hover:text-blue-600 dark:hover:text-blue-400"
                        >
                          {entry.label}
                        </Link>
                      ) : (
                        entry.label
                      )}
                    </h3>
                    <span
                      className={`text-[10px] font-bold uppercase px-1.5 py-0.5 border ${AUDIENCE_BADGE[entry.audience]}`}
                    >
                      {AUDIENCE_LABEL[entry.audience]}
                    </span>
                  </div>
                  <p className="text-[13px] leading-5 text-slate-600 dark:text-slate-400 mb-2">
                    {entry.description}
                  </p>
                  <p className="text-[12px] text-slate-500 dark:text-slate-500">
                    <span className="font-bold text-slate-700 dark:text-slate-300">Effect: </span>
                    {entry.effect}
                  </p>
                </div>
                <div className="text-[11px] font-mono text-slate-400 dark:text-slate-500 md:text-right md:max-w-[220px] break-all">
                  {entry.surface}
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}

      <footer className="mt-10 pt-6 border-t border-slate-200 dark:border-slate-800 text-[12px] text-slate-500 dark:text-slate-400">
        <p>
          Tables this map describes:{" "}
          <code className="text-slate-700 dark:text-slate-300">improvement_feedback</code>,{" "}
          <code className="text-slate-700 dark:text-slate-300">rater_feedback</code>,{" "}
          <code className="text-slate-700 dark:text-slate-300">feedback_decisions</code>,{" "}
          <code className="text-slate-700 dark:text-slate-300">story_events</code>,{" "}
          <code className="text-slate-700 dark:text-slate-300">sources.cluster_quality_score</code>.
        </p>
        <p className="mt-1.5">
          Live cron schedules:{" "}
          <Link
            href="/fa/dashboard/learning"
            className="text-blue-600 dark:text-blue-400 hover:underline"
          >
            /dashboard/learning
          </Link>
          {" "}for events + source trust;{" "}
          <Link
            href="/fa/dashboard/actions"
            className="text-blue-600 dark:text-blue-400 hover:underline"
          >
            /dashboard/actions
          </Link>
          {" "}for what fired today.
        </p>
      </footer>
    </div>
  );
}
