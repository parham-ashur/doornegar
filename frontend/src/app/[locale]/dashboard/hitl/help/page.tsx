"use client";

/**
 * HITL instructions page. One place that explains every control — what
 * each queue is for, when to use the split / freeze / arc-scaffold
 * endpoints, and what the review tiers mean. Parham keeps adding new
 * primitives; without this doc the menu becomes a pile of unmarked
 * buttons.
 */
export default function HitlHelp() {
  return (
    <div className="max-w-3xl">
      <h1 className="text-xl font-black text-slate-900 dark:text-white mb-2">
        HITL Tooling Guide
      </h1>
      <p className="text-[13px] text-slate-500 dark:text-slate-400 mb-6 leading-6">
        Each tool covers one place where the automated pipeline is unsure
        or wrong. This page lists what every control does and when to reach
        for it.
      </p>

      <Section title="Review Queue">
        <p>
          When a cluster grows too large or lingers too long, the guardrail
          pass flags it. Three tiers:
        </p>
        <Ul>
          <li>
            <b>Tier 1 (soft warn):</b> 100+ articles or a span of 3+ days between
            creation and last update. Informational — usually no action needed.
          </li>
          <li>
            <b>Tier 2 (strong warn):</b> 150+ articles or 5+ days. Open the story
            and review.
          </li>
          <li>
            <b>Tier 3 (propose freeze):</b> 200+ articles or 7+ days. If the cluster
            covers several events it should be <b>split</b>; if the story is over,
            <b>freeze</b> it so stale articles stop accumulating.
          </li>
          <li>
            <b>Single-source:</b> clusters where every article comes from one outlet.
            Removed from trending and queued for merge or hide.
          </li>
        </Ul>
      </Section>

      <Section title="Freeze">
        <p>
          A frozen story is skipped by the auto-matcher and every merge step,
          so no new articles attach to it. Use this once an event is over — it
          prevents late drift into a dumping-ground cluster. Always reversible.
        </p>
        <Endpoint method="POST" path="/api/v1/admin/hitl/stories/{id}/freeze" />
        <Endpoint method="POST" path="/api/v1/admin/hitl/stories/{id}/unfreeze" />
      </Section>

      <Section title="Split">
        <p>
          When one cluster is actually several events, name each sub-event with
          an explicit list of article IDs. The source story is frozen and the
          children can optionally live inside a new narrative arc. Telegram posts
          re-attach to the right child on the next linker pass.
        </p>
        <Endpoint method="POST" path="/api/v1/admin/hitl/stories/{id}/split" />
        <p className="mt-2">
          Niloofar can also propose <code>fix_type: split_story</code> in her
          audit reports; the same primitive runs when you confirm via
          <code>--apply-from</code>.
        </p>
      </Section>

      <Section title="Arc Scaffold">
        <p>
          When you already know a long story plays out in chapters (e.g. A → B →
          C → D), define the arc title and chapter titles in one call. For each
          chapter the system tries to match an existing cluster by title /
          keyword hint; if nothing matches it creates an empty placeholder so
          later articles attach there instead of somewhere noisier.
        </p>
        <Endpoint
          method="POST"
          path="/api/v1/admin/hitl/arcs/scaffold-preview"
          note="Dry run — nothing is written"
        />
        <Endpoint method="POST" path="/api/v1/admin/hitl/arcs/scaffold" />
      </Section>

      <Section title="Image Queue">
        <p>
          The homepage and the "related stories" strip at the bottom of story
          pages now hide stories whose only cover candidate is a source logo.
          Those stories show up in the <b>Stories without image</b> queue on the
          HITL index, ordered by priority. Click "Pick image" — the image picker
          pre-fills the search bar with the English title and shows story
          context so you don't have to tab back and forth.
        </p>
      </Section>

      <Section title="Telegram Triage">
        <p>
          Posts with a score between 0.30 and 0.40 aren't attached automatically
          (auto-attach threshold is 0.40). This is the decision-boundary queue —
          link a post to the right story, or detach it entirely.
        </p>
      </Section>

      <Section title="Source & Channel Classification">
        <p>
          If an outlet's production location or political alignment is wrong, fix
          it here. The 4-subgroup taxonomy (principlist / reformist / moderate
          diaspora / radical diaspora) is derived directly from these fields.
        </p>
      </Section>

      <Section title="Niloofar Audit">
        <p>
          Niloofar dumps a JSON sample of top stories for local review; apply her
          findings back with <code>--apply-from</code>. Fixes include: rename
          title, rewrite narratives, remove irrelevant article, merge two
          clusters, split a cluster, and refresh neutrality analysis.
        </p>
      </Section>

      <Section title="Story Events">
        <p>
          Every automated decision (attach, create, merge, tier-promote) and
          every HITL action (freeze, split, scaffold) is logged to
          <code>story_events</code>.
        </p>
        <Endpoint
          method="GET"
          path="/api/v1/admin/hitl/review-queue"
          note="Flagged clusters"
        />
        <Endpoint
          method="GET"
          path="/api/v1/admin/hitl/stories/{id}/events"
          note="Per-story timeline"
        />
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-7 border-t border-slate-200 dark:border-slate-800 pt-5">
      <h2 className="text-[15px] font-black text-slate-900 dark:text-white mb-2">
        {title}
      </h2>
      <div className="text-[13px] text-slate-600 dark:text-slate-300 leading-7 space-y-2">
        {children}
      </div>
    </section>
  );
}

function Ul({ children }: { children: React.ReactNode }) {
  return <ul className="list-disc pl-5 space-y-1">{children}</ul>;
}

function Endpoint({ method, path, note }: { method: string; path: string; note?: string }) {
  return (
    <div
      className="font-mono text-[11px] bg-slate-100 dark:bg-slate-800 px-2 py-1 inline-flex flex-wrap items-center gap-2 mr-2 mb-1"
      dir="ltr"
    >
      <span className="font-black">{method}</span>
      <span>{path}</span>
      {note && <span className="text-slate-500">— {note}</span>}
    </div>
  );
}
