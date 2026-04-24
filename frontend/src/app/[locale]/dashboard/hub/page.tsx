"use client";

/**
 * Dashboard Hub — single workflow-oriented landing page.
 *
 * Purpose: collapse "what needs me right now?" into one screen so Parham
 * doesn't have to scan the 1884-line main dashboard to find the day's
 * attention items. Sections are ordered by frequency of use:
 *
 *   1. ATTENTION — red/amber alerts (cost anomalies, ingest staleness,
 *      unscored articles, orphans).
 *   2. PROJECT — next-action checklist (IID legal, product backlog).
 *      Inline const below; edit this file to update. Status marks are
 *      persisted to localStorage so ticking a box survives reloads.
 *   3. HITL — keyboard-navigated jump list to the 8 HITL subpages with
 *      pending-count badges where available.
 *   4. NILOOFAR — latest audit summary.
 *   5. PIPELINE — ingest / cluster / score status from the existing
 *      /admin/dashboard endpoint.
 *
 * Keyboard shortcuts (Gmail-style two-stroke):
 *   g h → hub (this page)       g d → main dashboard
 *   g t → telegram triage       g s → sources
 *   g n → narrative reassign    g a → arcs
 *   g c → channels              g u → submissions
 *   g $ → cost                  g x → actions
 *   ?   → shortcut help overlay
 *
 * Non-breaking: the existing /dashboard main page stays the primary
 * entry point. The hub is linked from there and can replace it later
 * if it proves the better landing.
 */

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { adminHeaders, hasAdminToken } from "../hitl/_auth";
import OverviewPanels from "@/components/dashboard/OverviewPanels";
import {
  RefreshCw, AlertTriangle, CheckCircle2, Circle,
  Inbox, Activity, Keyboard, Gavel, Package, ExternalLink,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ───────────────────────────────────────────────────────────────
// Project priorities — inline const. Edit this file to update.
// Status persists to localStorage (key: "hub_checks") so ticking a
// box survives reloads without a backend round-trip.
// ───────────────────────────────────────────────────────────────

type Priority = {
  id: string;
  title: string;
  detail?: string;
  link?: { href: string; label: string };
};

const LEGAL_PRIORITIES: Priority[] = [
  {
    id: "legal.kandbaz",
    title: "Email Kandbaz for agrément préfectoral number",
    detail: "Required by art. L.123-11-3 Code de commerce. Draft email in legal/18 notes.",
  },
  {
    id: "legal.assembly",
    title: "Schedule video constitutive assembly (Parham + Afrooz + Sarah)",
    detail: "Sarah returns to Nice in 3 months — hybrid signing avoids that wait.",
  },
  {
    id: "legal.mail-sarah",
    title: "Post statutes + PV to Sarah in Lille (registered mail)",
    detail: "After video call. She signs and returns by post.",
  },
  {
    id: "legal.declare",
    title: "File on service-public.fr",
    detail: "PDFs: statutes, PV, attestation Kandbaz, dirigeants list.",
  },
  {
    id: "legal.joafe",
    title: "Await JOAFE publication (1–2 weeks after filing)",
  },
  {
    id: "legal.siret",
    title: "Request SIREN/SIRET from INSEE (Cerfa n°13973)",
  },
  {
    id: "legal.bank",
    title: "Open bank account (Qonto or Crédit Coopératif)",
  },
  {
    id: "legal.domain",
    title: "Buy institutid.org domain with WHOIS privacy",
    detail: "Parallel, can do anytime. Porkbun or Cloudflare Registrar.",
  },
  {
    id: "legal.protonmail",
    title: "Set up ProtonMail @institutid.org",
    detail: "After domain purchase.",
  },
  {
    id: "legal.first-grant",
    title: "Draft NLnet application (first easy grant win)",
    detail: "Ready to submit day the SIRET arrives.",
  },
];

const PRODUCT_PRIORITIES: Priority[] = [
  {
    id: "product.suspense",
    title: "Per-section Suspense boundaries on homepage",
    detail: "Stream hero first; park telegram sidebar behind Suspense.",
  },
  {
    id: "product.trending-ttfb",
    title: "Speed up /stories/trending TTFB",
    detail: "Currently ~2.7s. Investigate caching + query shape.",
  },
  {
    id: "product.sources-edge-cache",
    title: "Cache /api/v1/sources at Cloudflare edge",
  },
  {
    id: "product.budget-alerts",
    title: "Budget alerts on /dashboard/cost",
    detail: "Telegram webhook when daily > threshold.",
    link: { href: "/fa/dashboard/cost", label: "Cost dashboard" },
  },
  {
    id: "product.dispute-score",
    title: "LLM-computed dispute_score per story",
    detail: "Replace |state_pct - diaspora_pct| proxy.",
  },
  {
    id: "product.niloofar-split",
    title: "Add split-story fix_type to Niloofar",
  },
  {
    id: "product.auto-merge",
    title: "Auto-merge suggestions in Niloofar gather output",
  },
];

const OPS_PRIORITIES: Priority[] = [
  {
    id: "ops.tighten-auto-match",
    title: "Tighten AUTO_MATCH_COSINE 0.85 → 0.80 (if needed)",
    detail: "Only if small-target gate alone isn't enough to cap orphans.",
  },
  {
    id: "ops.niloofar-weekly-cap",
    title: "Cap Niloofar to 1 audit/story/week",
  },
  {
    id: "ops.embeddings-ledger",
    title: "Instrument embeddings in cost ledger",
    detail: "Currently skipped (sync API). Add a lightweight logger.",
  },
];

// ───────────────────────────────────────────────────────────────

type DashboardData = {
  data?: {
    articles?: { total?: number; last_24h?: number; without_farsi_title?: number };
    stories?: { total?: number; visible?: number; hidden?: number; with_summary?: number };
    telegram?: { channels?: number; active?: number; posts_24h?: number; total_posts?: number };
  };
  issues?: Array<{ severity: string; message: string }>;
  actions_needed?: string[];
  freshness_hours?: number | null;
  maintenance?: { status?: string; last_run?: string | null; next_step?: string | null };
};

type CostSummary = {
  today: { cost: number; calls: number };
  yesterday: { cost: number; calls: number };
  totals: { total_cost: number; calls: number };
};

type HITLLink = {
  key: string;           // e.g. "s" for sources
  label: string;
  href: string;
  icon: string;          // emoji
};

const HITL_LINKS: HITLLink[] = [
  { key: "t", label: "Telegram triage", href: "/fa/dashboard/hitl/telegram-triage", icon: "💬" },
  { key: "s", label: "Sources", href: "/fa/dashboard/hitl/sources", icon: "📡" },
  { key: "n", label: "Narrative reassign", href: "/fa/dashboard/hitl/narrative", icon: "📖" },
  { key: "a", label: "Arcs", href: "/fa/dashboard/hitl/arcs", icon: "🔀" },
  { key: "c", label: "Channels", href: "/fa/dashboard/hitl/channels", icon: "📢" },
  { key: "u", label: "Submissions", href: "/fa/dashboard/hitl/submissions", icon: "📬" },
  { key: "i", label: "Stock images", href: "/fa/dashboard/hitl/stock-images", icon: "🖼" },
];

const QUICK_LINKS: HITLLink[] = [
  { key: "d", label: "Main dashboard", href: "/fa/dashboard", icon: "📊" },
  { key: "$", label: "Cost", href: "/fa/dashboard/cost", icon: "💵" },
  { key: "x", label: "Actions", href: "/fa/dashboard/actions", icon: "⚙" },
  { key: "r", label: "Rate stories", href: "/fa/rate", icon: "⭐" },
];

// ───────────────────────────────────────────────────────────────

function useChecks() {
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  useEffect(() => {
    try {
      const raw = localStorage.getItem("hub_checks");
      if (raw) setChecks(JSON.parse(raw));
    } catch {}
  }, []);
  const toggle = (id: string) => {
    setChecks(prev => {
      const next = { ...prev, [id]: !prev[id] };
      try { localStorage.setItem("hub_checks", JSON.stringify(next)); } catch {}
      return next;
    });
  };
  return { checks, toggle };
}

function fmt$(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 0.01) return "$" + n.toFixed(4);
  return "$" + n.toFixed(2);
}

function fmtNum(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString("en-US");
}

export default function HubPage() {
  const router = useRouter();
  const [authed, setAuthed] = useState(false);
  const [tokenInput, setTokenInput] = useState("");
  const [data, setData] = useState<DashboardData | null>(null);
  const [cost, setCost] = useState<CostSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const { checks, toggle } = useChecks();
  const pendingKey = useRef<string | null>(null);

  // Auth
  useEffect(() => { setAuthed(hasAdminToken()); }, []);

  // Fetch data
  const fetchAll = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const h = adminHeaders();
      const [d, c] = await Promise.all([
        fetch(`${API}/api/v1/admin/dashboard`, { headers: h, cache: "no-store" }).then(r => r.ok ? r.json() : null),
        fetch(`${API}/api/v1/admin/cost/summary?window=24h`, { headers: h, cache: "no-store" }).then(r => r.ok ? r.json() : null),
      ]);
      setData(d);
      setCost(c);
    } catch (e: any) {
      setErr(e?.message || "Error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (authed) fetchAll(); }, [authed, fetchAll]);
  useEffect(() => {
    if (!authed) return;
    const id = setInterval(fetchAll, 60000);
    return () => clearInterval(id);
  }, [authed, fetchAll]);

  // Keyboard shortcuts: `?` for help, `g <key>` for navigation.
  useEffect(() => {
    if (!authed) return;
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      if (e.key === "?") {
        setShowHelp(s => !s);
        return;
      }
      if (e.key === "Escape") {
        setShowHelp(false);
        pendingKey.current = null;
        return;
      }
      if (pendingKey.current === "g") {
        const all = [...HITL_LINKS, ...QUICK_LINKS];
        const match = all.find(l => l.key === e.key);
        pendingKey.current = null;
        if (match) {
          e.preventDefault();
          router.push(match.href);
        } else if (e.key === "h") {
          // already on hub
        }
        return;
      }
      if (e.key === "g") {
        pendingKey.current = "g";
        setTimeout(() => { if (pendingKey.current === "g") pendingKey.current = null; }, 1200);
        return;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [authed, router]);

  if (!authed) {
    return (
      <div className="p-8 max-w-md mx-auto">
        <h1 className="text-xl font-bold mb-4">Admin sign-in</h1>
        <input
          type="password"
          className="w-full border border-slate-300 dark:border-slate-700 px-3 py-2 bg-transparent"
          placeholder="admin token"
          value={tokenInput}
          onChange={e => setTokenInput(e.target.value)}
        />
        <button
          className="mt-3 px-4 py-2 bg-slate-900 text-white dark:bg-white dark:text-slate-900"
          onClick={() => {
            localStorage.setItem("doornegar_admin_token", tokenInput);
            setAuthed(true);
          }}
        >
          Sign in
        </button>
      </div>
    );
  }

  // Compose attention items from dashboard response.
  const issues = data?.issues || [];
  const urgentIssues = issues.filter(i => i.severity === "error" || i.severity === "warning");
  const freshHours = data?.freshness_hours ?? null;
  const freshStale = typeof freshHours === "number" && freshHours > 6;
  const costToday = cost?.today?.cost ?? null;
  const costSpike = costToday != null && cost?.yesterday?.cost != null
    && cost.yesterday.cost > 0.01
    && costToday > cost.yesterday.cost * 1.5;

  // Tiny helpers to pluck the nested dashboard response.
  const dd = data?.data;

  return (
    <div className="p-6 max-w-6xl mx-auto text-slate-900 dark:text-slate-100">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-black">Doornegar Hub</h1>
          <p className="text-xs text-slate-500 mt-1">Workflow-oriented landing. Press <kbd className="px-1.5 py-0.5 border border-slate-300 dark:border-slate-700 text-[10px] font-mono">?</kbd> for shortcuts.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowHelp(true)} className="p-2 border border-slate-300 dark:border-slate-700 hover:border-slate-500" title="Shortcuts">
            <Keyboard className="w-4 h-4" />
          </button>
          <button onClick={fetchAll} className="p-2 border border-slate-300 dark:border-slate-700 hover:border-slate-500" title="Refresh">
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {err && (
        <div className="mb-4 px-4 py-3 border border-red-300 bg-red-50 dark:bg-red-950/40 text-red-800 dark:text-red-200 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {err}
        </div>
      )}

      {/* Overview panels — rolled up 7d cost, ingest health, review
          queue load. Each card links to its full page. */}
      <OverviewPanels />

      {/* ATTENTION */}
      <Section icon={<AlertTriangle className="w-4 h-4 text-amber-500" />} title="Attention" dir="ltr">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricTile
            label="Cost — today"
            value={fmt$(costToday)}
            sub={cost ? `${fmtNum(cost.today.calls)} calls` : undefined}
            tone={costSpike ? "amber" : "ok"}
          />
          <MetricTile
            label="Cost — yesterday"
            value={fmt$(cost?.yesterday?.cost ?? null)}
            sub={cost ? `${fmtNum(cost.yesterday.calls)} calls` : undefined}
          />
          <MetricTile
            label="Last ingest"
            value={freshHours == null ? "—" : `${freshHours < 1 ? freshHours.toFixed(1) : Math.round(freshHours)}h ago`}
            tone={freshStale ? "amber" : "ok"}
          />
          <MetricTile
            label="Visible stories"
            value={fmtNum(dd?.stories?.visible ?? null)}
            sub={dd?.stories?.hidden != null ? `${fmtNum(dd.stories.hidden)} hidden` : undefined}
          />
        </div>
        {urgentIssues.length > 0 && (
          <ul className="mt-4 space-y-1">
            {urgentIssues.slice(0, 8).map((i, idx) => (
              <li key={idx} className="text-sm flex items-start gap-2">
                <AlertTriangle className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${i.severity === "error" ? "text-red-500" : "text-amber-500"}`} />
                <span className={i.severity === "error" ? "text-red-700 dark:text-red-300" : "text-amber-700 dark:text-amber-300"}>
                  {i.message}
                </span>
              </li>
            ))}
          </ul>
        )}
        {urgentIssues.length === 0 && !costSpike && !freshStale && (
          <p className="mt-4 text-sm text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4" /> Nothing urgent.
          </p>
        )}
      </Section>

      {/* PROJECT MANAGEMENT */}
      <Section icon={<Gavel className="w-4 h-4 text-slate-500" />} title="Project Management" dir="ltr">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <PriorityColumn title="IID — Legal" items={LEGAL_PRIORITIES} checks={checks} toggle={toggle} />
          <PriorityColumn title="Product" items={PRODUCT_PRIORITIES} checks={checks} toggle={toggle} />
          <PriorityColumn title="Ops" items={OPS_PRIORITIES} checks={checks} toggle={toggle} />
        </div>
        <p className="mt-4 text-[11px] text-slate-500">
          Edit <code className="font-mono text-[10px]">frontend/src/app/[locale]/dashboard/hub/page.tsx</code> to add or remove items.
          Completion marks persist to localStorage.
        </p>
      </Section>

      {/* HITL */}
      <Section icon={<Inbox className="w-4 h-4 text-slate-500" />} title="HITL Queue" dir="ltr">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {HITL_LINKS.map(l => (
            <Link
              key={l.key}
              href={l.href}
              className="flex items-center gap-3 px-3 py-2.5 border border-slate-200 dark:border-slate-800 hover:border-blue-400 dark:hover:border-blue-600 transition-colors group"
            >
              <span className="text-lg">{l.icon}</span>
              <div className="flex-1 min-w-0">
                <div className="text-sm text-slate-700 dark:text-slate-200 group-hover:text-blue-700 dark:group-hover:text-blue-300">
                  {l.label}
                </div>
                <div className="text-[10px] text-slate-400 font-mono">g → {l.key}</div>
              </div>
              <ExternalLink className="w-3 h-3 text-slate-400 group-hover:text-blue-500" />
            </Link>
          ))}
        </div>
      </Section>

      {/* QUICK LINKS */}
      <Section icon={<Package className="w-4 h-4 text-slate-500" />} title="Quick Links" dir="ltr">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {QUICK_LINKS.map(l => (
            <Link
              key={l.key}
              href={l.href}
              className="flex items-center gap-3 px-3 py-2.5 border border-slate-200 dark:border-slate-800 hover:border-blue-400 dark:hover:border-blue-600 transition-colors group"
            >
              <span className="text-lg">{l.icon}</span>
              <div className="flex-1 min-w-0">
                <div className="text-sm text-slate-700 dark:text-slate-200 group-hover:text-blue-700 dark:group-hover:text-blue-300">
                  {l.label}
                </div>
                <div className="text-[10px] text-slate-400 font-mono">g → {l.key}</div>
              </div>
            </Link>
          ))}
        </div>
      </Section>

      {/* PIPELINE */}
      <Section icon={<Activity className="w-4 h-4 text-slate-500" />} title="Pipeline" dir="ltr">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricTile label="Articles — 24h" value={fmtNum(dd?.articles?.last_24h ?? null)} sub={`total ${fmtNum(dd?.articles?.total ?? null)}`} />
          <MetricTile label="Without FA title" value={fmtNum(dd?.articles?.without_farsi_title ?? null)} tone={(dd?.articles?.without_farsi_title ?? 0) > 50 ? "amber" : "ok"} />
          <MetricTile label="Channels" value={`${fmtNum(dd?.telegram?.active ?? null)} / ${fmtNum(dd?.telegram?.channels ?? null)}`} sub="active / total" />
          <MetricTile label="Posts — 24h" value={fmtNum(dd?.telegram?.posts_24h ?? null)} />
        </div>
        {data?.maintenance?.status && (
          <div className="mt-4 text-xs text-slate-500">
            <span className="font-bold">Maintenance:</span> {data.maintenance.status}
            {data.maintenance.last_run && <> · last run {new Date(data.maintenance.last_run).toLocaleString("fa-IR")}</>}
            {data.maintenance.next_step && <> · next: {data.maintenance.next_step}</>}
          </div>
        )}
      </Section>

      {/* Help overlay */}
      {showHelp && (
        <div
          className="fixed inset-0 bg-slate-900/70 backdrop-blur-sm z-50 flex items-center justify-center p-6"
          onClick={() => setShowHelp(false)}
        >
          <div
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 max-w-md w-full"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold">Keyboard shortcuts</h3>
              <button onClick={() => setShowHelp(false)} className="text-xs text-slate-400 hover:text-slate-600">close (esc)</button>
            </div>
            <div className="space-y-4 text-sm">
              <div>
                <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">HITL</div>
                <ul className="space-y-1">
                  {HITL_LINKS.map(l => (
                    <li key={l.key} className="flex justify-between">
                      <span className="text-slate-600 dark:text-slate-300">{l.label}</span>
                      <kbd className="font-mono text-[11px] text-slate-500">g {l.key}</kbd>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">Pages</div>
                <ul className="space-y-1">
                  {QUICK_LINKS.map(l => (
                    <li key={l.key} className="flex justify-between">
                      <span className="text-slate-600 dark:text-slate-300">{l.label}</span>
                      <kbd className="font-mono text-[11px] text-slate-500">g {l.key}</kbd>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="pt-2 border-t border-slate-200 dark:border-slate-800">
                <div className="flex justify-between">
                  <span className="text-slate-600 dark:text-slate-300">Toggle help</span>
                  <kbd className="font-mono text-[11px] text-slate-500">?</kbd>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────────────
// Subcomponents
// ───────────────────────────────────────────────────────────────

function Section({ icon, title, children, dir = "rtl" }: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  dir?: "rtl" | "ltr";
}) {
  return (
    <section dir={dir} className="mb-8">
      <div className="flex items-center gap-2 mb-3 pb-2 border-b border-slate-200 dark:border-slate-800">
        {icon}
        <h2 className="text-sm font-black uppercase tracking-wider text-slate-700 dark:text-slate-300">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function MetricTile({ label, value, sub, tone = "ok" }: {
  label: string;
  value: string;
  sub?: string;
  tone?: "ok" | "amber" | "red";
}) {
  const toneClass = tone === "red"
    ? "border-red-300 dark:border-red-900 bg-red-50 dark:bg-red-950/30"
    : tone === "amber"
      ? "border-amber-300 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/30"
      : "border-slate-200 dark:border-slate-800";
  return (
    <div className={`border p-3 ${toneClass}`}>
      <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">{label}</div>
      <div className="mt-1 text-xl font-black font-mono">{value}</div>
      {sub && <div className="mt-0.5 text-[10px] text-slate-500">{sub}</div>}
    </div>
  );
}

function PriorityColumn({ title, items, checks, toggle }: {
  title: string;
  items: Priority[];
  checks: Record<string, boolean>;
  toggle: (id: string) => void;
}) {
  const doneCount = items.filter(i => checks[i.id]).length;
  return (
    <div>
      <div className="flex items-center justify-between mb-2 pb-1 border-b border-slate-100 dark:border-slate-800">
        <h3 className="text-[11px] font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider">{title}</h3>
        <span className="text-[10px] text-slate-400 font-mono">{doneCount}/{items.length}</span>
      </div>
      <ul className="space-y-2">
        {items.map(p => {
          const done = !!checks[p.id];
          return (
            <li key={p.id} className="flex items-start gap-2 text-sm">
              <button
                onClick={() => toggle(p.id)}
                className="mt-0.5 shrink-0 text-slate-400 hover:text-blue-500"
                aria-label={done ? "Mark incomplete" : "Mark complete"}
              >
                {done ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                ) : (
                  <Circle className="w-4 h-4" />
                )}
              </button>
              <div className="flex-1 min-w-0">
                <div className={`text-[13px] leading-5 ${done ? "text-slate-400 line-through" : "text-slate-700 dark:text-slate-200"}`}>
                  {p.title}
                </div>
                {p.detail && !done && (
                  <div className="text-[11px] text-slate-500 mt-0.5 leading-4">{p.detail}</div>
                )}
                {p.link && !done && (
                  <Link href={p.link.href} className="text-[11px] text-blue-600 dark:text-blue-400 hover:underline mt-0.5 inline-block">
                    {p.link.label} →
                  </Link>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
