"use client";

import { useEffect, useState } from "react";
import { ArrowLeft, Database, Globe, Server, Cpu, MessageSquare, Brain, Newspaper, Users, Shield, ChevronDown, ChevronUp } from "lucide-react";
import Link from "next/link";

const ADMIN_PASS = "doornegar2026";

interface ComponentInfo {
  id: string;
  name: string;
  icon: React.ReactNode;
  color: string;
  description: string;
  tech: string;
  files: string[];
  functions: string[];
  connections: string[];
}

const components: ComponentInfo[] = [
  {
    id: "frontend",
    name: "Frontend",
    icon: <Globe className="h-5 w-5" />,
    color: "border-blue-500 bg-blue-50 dark:bg-blue-900/10",
    description: "Next.js 14 app with RTL Farsi interface. Renders the public website: homepage, story details, sources, blindspots.",
    tech: "Next.js 14, Tailwind CSS, next-intl, TypeScript",
    files: [
      "frontend/src/app/[locale]/page.tsx — Homepage (NYTimes layout)",
      "frontend/src/app/[locale]/stories/[id]/page.tsx — Story detail",
      "frontend/src/app/[locale]/dashboard/page.tsx — Admin dashboard",
      "frontend/src/components/story/StoryAnalysisPanel.tsx — AI summary display",
      "frontend/src/components/story/ArticleFilterList.tsx — Article list with filters",
      "frontend/src/components/feedback/ — Rater feedback components",
      "frontend/src/components/common/SafeImage.tsx — Image with fallback",
    ],
    functions: [
      "Fetches stories/sources from backend API",
      "Displays AI-generated summaries and bias analysis",
      "Per-side views (state/independent/diaspora)",
      "Rater feedback (article relevance, summary rating)",
      "Admin dashboard with pipeline controls",
    ],
    connections: ["Backend API (FastAPI)"],
  },
  {
    id: "backend",
    name: "Backend API",
    icon: <Server className="h-5 w-5" />,
    color: "border-emerald-500 bg-emerald-50 dark:bg-emerald-900/10",
    description: "FastAPI server handling all data operations, API endpoints, and pipeline orchestration.",
    tech: "FastAPI, SQLAlchemy 2 (async), Pydantic, Uvicorn",
    files: [
      "backend/app/main.py — App setup, CORS, static files",
      "backend/app/api/v1/stories.py — Story endpoints + analysis",
      "backend/app/api/v1/admin.py — Dashboard, pipeline triggers, rater mgmt",
      "backend/app/api/v1/feedback.py — Rater feedback endpoints",
      "backend/app/api/v1/ratings.py — Blind rating system",
      "backend/app/config.py — All configuration (env vars)",
    ],
    functions: [
      "GET /api/v1/stories/trending — Homepage stories",
      "GET /api/v1/stories/{id}/analysis — Cached AI summary",
      "POST /api/v1/stories/{id}/summarize — Generate summary via OpenAI",
      "PATCH /api/v1/admin/stories/{id} — Edit story title/summary",
      "GET /api/v1/admin/dashboard — System metrics",
      "POST /api/v1/admin/raters/create — Create rater account",
      "POST /api/v1/feedback/* — Store rater feedback",
    ],
    connections: ["PostgreSQL", "Redis", "OpenAI API", "Frontend"],
  },
  {
    id: "ingestion",
    name: "Data Ingestion",
    icon: <Newspaper className="h-5 w-5" />,
    color: "border-amber-500 bg-amber-50 dark:bg-amber-900/10",
    description: "Fetches articles from RSS feeds and Telegram channels. Converts Telegram posts into articles.",
    tech: "feedparser, httpx, trafilatura, telethon",
    files: [
      "backend/app/services/ingestion.py — RSS feed fetching",
      "backend/app/services/telegram_service.py — Telegram channel scraping + post→article conversion",
      "backend/app/services/seed.py — Source seeding (18 outlets)",
      "backend/app/services/seed_telegram.py — Telegram channel seeding",
    ],
    functions: [
      "Fetch RSS from 18 sources (BBC, Iran Intl, Press TV, etc.)",
      "Fetch Telegram posts from 9 channels",
      "Convert Telegram posts to Article records",
      "Extract images (og:image, media tags, Wikimedia fallback)",
      "Detect language, parse dates",
    ],
    connections: ["RSS Feeds (external)", "Telegram API", "PostgreSQL"],
  },
  {
    id: "nlp",
    name: "NLP Processing",
    icon: <Cpu className="h-5 w-5" />,
    color: "border-purple-500 bg-purple-50 dark:bg-purple-900/10",
    description: "Processes raw articles: normalize text, translate titles, generate embeddings, extract keywords.",
    tech: "sentence-transformers, OpenAI GPT-4o-mini, BeautifulSoup",
    files: [
      "backend/app/services/nlp_pipeline.py — Main NLP pipeline",
      "backend/app/nlp/persian.py — Persian text normalization",
      "backend/app/nlp/embeddings.py — Embedding generation",
    ],
    functions: [
      "Normalize Persian text",
      "Translate English titles to Farsi (OpenAI batch)",
      "Generate 384-dim embeddings (MiniLM)",
      "Extract keywords",
      "Fetch og:image for articles without images",
      "Search Wikimedia for free images",
    ],
    connections: ["OpenAI API", "PostgreSQL"],
  },
  {
    id: "clustering",
    name: "Story Clustering",
    icon: <Brain className="h-5 w-5" />,
    color: "border-red-500 bg-red-50 dark:bg-red-900/10",
    description: "Groups articles into stories using LLM. Incremental: matches new articles to existing stories first, then creates new clusters.",
    tech: "OpenAI GPT-4o-mini, SQLAlchemy",
    files: [
      "backend/app/services/clustering.py — LLM-based incremental clustering",
    ],
    functions: [
      "Step 1: Match new articles to existing stories (LLM)",
      "Step 2: Cluster remaining into new stories (LLM)",
      "Step 3: Promote hidden stories (≥5 articles → visible)",
      "Step 4: Merge duplicate hidden stories",
      "Compute coverage flags (state/diaspora/independent)",
      "Calculate trending scores",
      "Iran-only filtering",
    ],
    connections: ["OpenAI API", "PostgreSQL"],
  },
  {
    id: "analysis",
    name: "AI Analysis",
    icon: <Brain className="h-5 w-5" />,
    color: "border-indigo-500 bg-indigo-50 dark:bg-indigo-900/10",
    description: "Generates per-story summaries, per-side analysis, bias comparison, and framing labels using article content.",
    tech: "OpenAI GPT-4o-mini",
    files: [
      "backend/app/services/story_analysis.py — Summary + bias generation",
      "backend/app/services/bias_scoring.py — Per-article bias scoring",
    ],
    functions: [
      "Overall summary (3-4 sentences from full content)",
      "Per-side summaries (state / independent / diaspora)",
      "Bias comparison between sides",
      "Framing labels per side (threat, resistance, crisis, etc.)",
      "Pre-generated and cached in DB",
    ],
    connections: ["OpenAI API", "PostgreSQL"],
  },
  {
    id: "database",
    name: "Database",
    icon: <Database className="h-5 w-5" />,
    color: "border-slate-500 bg-slate-50 dark:bg-slate-900/10",
    description: "PostgreSQL with pgvector extension. Stores all articles, stories, sources, ratings, and feedback.",
    tech: "PostgreSQL 16, pgvector, Alembic migrations",
    files: [
      "backend/app/models/article.py — Article model",
      "backend/app/models/story.py — Story model",
      "backend/app/models/source.py — Source model (18 outlets)",
      "backend/app/models/social.py — Telegram channels + posts",
      "backend/app/models/feedback.py — Rater feedback",
      "backend/app/models/user.py — Rater accounts",
      "backend/alembic/ — Database migrations",
    ],
    functions: [
      "10 tables: articles, stories, sources, bias_scores, users, community_ratings, rater_feedback, telegram_channels, telegram_posts, ingestion_log",
      "384-dim vector embeddings (pgvector)",
      "JSONB fields for keywords, framing labels, entities",
      "UUID primary keys",
    ],
    connections: ["Backend API", "NLP Pipeline", "Clustering", "Analysis"],
  },
  {
    id: "telegram",
    name: "Telegram Integration",
    icon: <MessageSquare className="h-5 w-5" />,
    color: "border-sky-500 bg-sky-50 dark:bg-sky-900/10",
    description: "Monitors 9 Telegram channels for Iranian news. Primary source for inside-Iran media (RSS often geo-blocked).",
    tech: "Telethon, asyncio",
    files: [
      "backend/app/services/telegram_service.py — Channel scraping + conversion",
    ],
    functions: [
      "9 active channels: BBC Persian, Tasnim, Fars, Khabar Online, Press TV, Radio Farda, Radio Zamaneh, Zeitoons, Iran International",
      "Fetch latest posts, extract URLs, clean markdown",
      "Convert posts to Article records",
      "Link posts to stories by URL matching",
    ],
    connections: ["Telegram API (external)", "PostgreSQL"],
  },
  {
    id: "feedback",
    name: "Rating & Feedback",
    icon: <Users className="h-5 w-5" />,
    color: "border-pink-500 bg-pink-50 dark:bg-pink-900/10",
    description: "Invite-only rating system. Raters provide blind article ratings and feedback on AI analysis quality.",
    tech: "JWT auth, bcrypt",
    files: [
      "backend/app/api/v1/ratings.py — Blind rating endpoints",
      "backend/app/api/v1/feedback.py — Feedback endpoints",
      "backend/app/services/auth.py — JWT authentication",
      "frontend/src/app/[locale]/rate/page.tsx — Rating interface",
      "frontend/src/components/feedback/ — Feedback UI components",
    ],
    functions: [
      "Blind article rating (5 dimensions)",
      "Article relevance feedback (thumbs up/down)",
      "Summary accuracy rating (1-5 stars)",
      "Source categorization suggestions",
      "Invite-only accounts (admin creates)",
    ],
    connections: ["PostgreSQL", "Frontend"],
  },
  {
    id: "maintenance",
    name: "Auto-Maintenance",
    icon: <Shield className="h-5 w-5" />,
    color: "border-teal-500 bg-teal-50 dark:bg-teal-900/10",
    description: "Automated pipeline that runs every 4 hours. Ingests, processes, clusters, summarizes, fixes issues, and updates docs.",
    tech: "macOS LaunchAgent (local), Celery Beat (production)",
    files: [
      "backend/auto_maintenance.py — Full maintenance cycle",
      "backend/qa_check.py — Quality assurance checks",
      "backend/manage.py — CLI management commands",
    ],
    functions: [
      "Step 1: Ingest (RSS + Telegram)",
      "Step 2: Process (NLP, translate, embed)",
      "Step 3: Cluster (match existing + create new)",
      "Step 4: Summarize (new stories)",
      "Step 5: Auto-fix (translate English titles, clean source names)",
      "Step 6: Update project docs (metrics, logs)",
      "Runs every 4h via LaunchAgent or Celery",
    ],
    connections: ["All backend services", "Project management docs"],
  },
];

function ComponentCard({ comp, isExpanded, onToggle }: { comp: ComponentInfo; isExpanded: boolean; onToggle: () => void }) {
  return (
    <div className={`border ${comp.color} p-5`}>
      <button onClick={onToggle} className="w-full flex items-center justify-between text-left">
        <div className="flex items-center gap-3">
          <div className="text-slate-700 dark:text-slate-300">{comp.icon}</div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">{comp.name}</h3>
            <p className="text-xs text-slate-500">{comp.tech}</p>
          </div>
        </div>
        {isExpanded ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
      </button>

      {isExpanded && (
        <div className="mt-4 space-y-4">
          <p className="text-sm text-slate-600 dark:text-slate-400">{comp.description}</p>

          <div>
            <h4 className="text-xs font-bold text-slate-700 dark:text-slate-300 mb-2">Key Functions</h4>
            <ul className="space-y-1">
              {comp.functions.map((f, i) => (
                <li key={i} className="text-xs text-slate-500 flex items-start gap-2">
                  <span className="text-slate-400 mt-0.5">•</span> {f}
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h4 className="text-xs font-bold text-slate-700 dark:text-slate-300 mb-2">Files</h4>
            <ul className="space-y-1">
              {comp.files.map((f, i) => (
                <li key={i} className="text-[11px] font-mono text-slate-500">{f}</li>
              ))}
            </ul>
          </div>

          <div>
            <h4 className="text-xs font-bold text-slate-700 dark:text-slate-300 mb-2">Connects to</h4>
            <div className="flex flex-wrap gap-2">
              {comp.connections.map((c, i) => (
                <span key={i} className="text-[11px] px-2 py-0.5 border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400">{c}</span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ArchitecturePage() {
  const [authed, setAuthed] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (typeof window !== "undefined" && localStorage.getItem("doornegar_admin") === "true") {
      setAuthed(true);
    }
  }, []);

  if (!authed) {
    return (
      <div className="mx-auto max-w-sm px-4 py-24 text-center">
        <p className="text-slate-500">Access the <Link href="./." className="text-blue-600 hover:underline">dashboard</Link> first to authenticate.</p>
      </div>
    );
  }

  const toggleAll = () => {
    if (expanded.size === components.length) {
      setExpanded(new Set());
    } else {
      setExpanded(new Set(components.map(c => c.id)));
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <Link href="./." className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300">
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white">System Architecture</h1>
          </div>
          <p className="text-sm text-slate-500">Interactive map of all components. Click to expand.</p>
        </div>
        <button onClick={toggleAll} className="text-xs border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800">
          {expanded.size === components.length ? "Collapse All" : "Expand All"}
        </button>
      </div>

      {/* Pipeline flow */}
      <div className="mb-8 border border-slate-200 dark:border-slate-800 p-5">
        <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Data Pipeline Flow</h2>
        <div className="flex items-center gap-2 flex-wrap text-xs">
          {["RSS Feeds", "→", "Telegram", "→", "Ingest", "→", "NLP Process", "→", "Cluster (LLM)", "→", "Summarize (LLM)", "→", "Frontend"].map((item, i) => (
            item === "→" ? (
              <span key={i} className="text-slate-400">→</span>
            ) : (
              <span key={i} className="px-2 py-1 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 font-medium">{item}</span>
            )
          ))}
        </div>
      </div>

      {/* Component grid */}
      <div className="grid gap-4 sm:grid-cols-2">
        {components.map((comp) => (
          <ComponentCard
            key={comp.id}
            comp={comp}
            isExpanded={expanded.has(comp.id)}
            onToggle={() => {
              const next = new Set(expanded);
              if (next.has(comp.id)) next.delete(comp.id);
              else next.add(comp.id);
              setExpanded(next);
            }}
          />
        ))}
      </div>
    </div>
  );
}
