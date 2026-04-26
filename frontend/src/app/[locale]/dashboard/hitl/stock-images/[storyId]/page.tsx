"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { adminHeaders, hasAdminToken } from "../../_auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Source = "article" | "wikimedia" | "unsplash";

interface Photo {
  id: string;
  thumb_url: string;
  regular_url: string;
  raw_url: string;
  alt: string | null;
  author_name: string | null;
  author_url: string | null;
  // Source-specific extras (any may be undefined depending on the tab)
  unsplash_url?: string | null;
  wikimedia_url?: string | null;
  license?: string | null;
  article_title_fa?: string | null;
  source_name_fa?: string | null;
  published_at?: string | null;
  width?: number;
  height?: number;
}

interface StoryContext {
  id: string;
  title_fa: string;
  title_en: string;
  summary_fa: string | null;
  article_count: number;
  source_count: number;
  first_published_at: string | null;
}

// Trim title down to search-friendly English keywords: drop leading numbers
// (dates, counts that picker APIs ignore), collapse whitespace, cap at 7
// words so we don't over-constrain the query. Title_en from Niloofar tends
// to be an event sentence — the first clause is the richest search signal.
function toSearchQuery(titleEn: string): string {
  if (!titleEn) return "";
  const firstClause = titleEn.split(/[;:]/)[0] || titleEn;
  const words = firstClause
    .replace(/[\d,./()\-—]+/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 2);
  return words.slice(0, 7).join(" ").trim();
}

export default function StockImagesPage() {
  const params = useParams<{ storyId: string }>();
  const storyId = params.storyId;
  const [authed, setAuthed] = useState(false);
  const [token, setToken] = useState("");
  const [source, setSource] = useState<Source>("article");
  const [query, setQuery] = useState("");
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [loading, setLoading] = useState(false);
  const [pinning, setPinning] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [story, setStory] = useState<StoryContext | null>(null);
  const [storyLoading, setStoryLoading] = useState(true);
  const [articleImagesLoaded, setArticleImagesLoaded] = useState(false);

  useEffect(() => {
    setAuthed(hasAdminToken());
  }, []);

  useEffect(() => {
    if (!storyId) return;
    let cancelled = false;
    fetch(`${API}/api/v1/stories/${storyId}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (cancelled || !d) {
          setStoryLoading(false);
          return;
        }
        const ctx: StoryContext = {
          id: d.id,
          title_fa: d.title_fa,
          title_en: d.title_en,
          summary_fa: d.summary_fa || null,
          article_count: d.article_count || 0,
          source_count: d.source_count || 0,
          first_published_at: d.first_published_at || null,
        };
        setStory(ctx);
        if (!query.trim()) {
          setQuery(toSearchQuery(ctx.title_en));
        }
        setStoryLoading(false);
      })
      .catch(() => {
        if (!cancelled) setStoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storyId]);

  const loadArticleImages = async () => {
    if (!authed || !storyId) return;
    setLoading(true);
    setPhotos([]);
    try {
      const res = await fetch(
        `${API}/api/v1/admin/hitl/stories/${storyId}/article-images`,
        { headers: adminHeaders() }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setMsg(err.detail || "Could not load article images");
        return;
      }
      const data = await res.json();
      setPhotos(data.results || []);
      setArticleImagesLoaded(true);
    } finally {
      setLoading(false);
    }
  };

  // Auto-load article-images tab on first auth so the curator immediately
  // sees the existing photos without an extra click. Other tabs still
  // require a search.
  useEffect(() => {
    if (authed && source === "article" && !articleImagesLoaded) {
      void loadArticleImages();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authed, source]);

  const search = async () => {
    if (source === "article") {
      void loadArticleImages();
      return;
    }
    if (!query.trim()) return;
    setLoading(true);
    setPhotos([]);
    try {
      const path =
        source === "wikimedia"
          ? `wikimedia-search?q=${encodeURIComponent(query)}&per_page=12`
          : `unsplash-search?q=${encodeURIComponent(query)}&per_page=9`;
      const res = await fetch(`${API}/api/v1/admin/hitl/${path}`, {
        headers: adminHeaders(),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setMsg(err.detail || "Search error");
        return;
      }
      const data = await res.json();
      setPhotos(data.results || []);
    } finally {
      setLoading(false);
    }
  };

  const pin = async (p: Photo) => {
    setPinning(p.id);
    setMsg("");
    const res = await fetch(`${API}/api/v1/admin/hitl/stories/${storyId}/pin-image`, {
      method: "POST",
      headers: { ...adminHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({
        image_url: p.raw_url || p.regular_url,
        author_name: p.author_name,
        author_url: p.author_url,
      }),
    });
    setPinning(null);
    if (res.ok) {
      const data = await res.json();
      setMsg(`Pinned ✓  ${data.r2_url}`);
    } else {
      const err = await res.json().catch(() => ({}));
      setMsg(err.detail || "Error");
    }
  };

  const tabs = useMemo(
    () =>
      [
        { id: "article" as const, label: "Article images", hint: "From this story's articles" },
        { id: "wikimedia" as const, label: "Wikimedia", hint: "Best for named people" },
        { id: "unsplash" as const, label: "Unsplash", hint: "Generic stock" },
      ],
    []
  );

  if (!authed) {
    return (
      <div>
        <h1 className="text-xl font-black mb-4">Pick image</h1>
        <p className="text-[13px] mb-3">Admin token:</p>
        <div className="flex gap-2">
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            dir="ltr"
            className="px-3 py-2 text-[13px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 w-96"
          />
          <button
            type="button"
            onClick={() => {
              localStorage.setItem("doornegar_admin_token", token);
              setAuthed(true);
            }}
            className="px-4 py-2 text-[13px] bg-blue-600 text-white"
          >
            Save
          </button>
        </div>
      </div>
    );
  }

  const showSearchBar = source !== "article";

  return (
    <div>
      <a
        href={`/fa/stories/${storyId}`}
        target="_blank"
        rel="noreferrer"
        className="text-[12px] text-blue-500 mb-2 block"
      >
        ← Open story page
      </a>
      <h1 className="text-xl font-black text-slate-900 dark:text-white mb-4">
        Pick image
      </h1>

      {storyLoading && (
        <div className="mb-5 text-[12px] text-slate-400">Loading story context…</div>
      )}
      {story && !storyLoading && (
        <div className="mb-5 border-2 border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 p-4">
          <h2 className="text-[15px] font-black text-slate-900 dark:text-white mb-1 leading-6">
            {story.title_fa}
          </h2>
          <p
            className="text-[12px] text-slate-500 dark:text-slate-400 mb-2"
            dir="ltr"
          >
            {story.title_en}
          </p>
          {story.summary_fa && (
            <p className="text-[13px] text-slate-600 dark:text-slate-300 leading-6 mb-2">
              {story.summary_fa}
            </p>
          )}
          <div className="text-[11px] text-slate-400" dir="ltr">
            {story.source_count} source{story.source_count === 1 ? "" : "s"} ·{" "}
            {story.article_count} article{story.article_count === 1 ? "" : "s"}
            {story.first_published_at && (
              <> · {new Date(story.first_published_at).toLocaleDateString("en-US")}</>
            )}
          </div>
        </div>
      )}

      <div className="flex gap-1 mb-5 border-b border-slate-200 dark:border-slate-800">
        {tabs.map((t) => {
          const active = source === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => {
                setSource(t.id);
                setMsg("");
                setPhotos([]);
                if (t.id === "article") void loadArticleImages();
              }}
              className={
                "px-4 py-2 text-[13px] -mb-px border-b-2 " +
                (active
                  ? "border-blue-600 text-slate-900 dark:text-white font-semibold"
                  : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300")
              }
            >
              {t.label}
              <span className="ml-2 text-[11px] text-slate-400">{t.hint}</span>
            </button>
          );
        })}
      </div>

      {showSearchBar ? (
        <>
          <p className="text-[13px] text-slate-500 mb-3 leading-6">
            {source === "wikimedia"
              ? "Wikimedia Commons hosts free-to-use photos and works best for named people (politicians, officials) and well-known places. License is shown on each result."
              : "Search bar is pre-filled with English keywords from the story title. Edit before searching if you want. Unsplash is generic stock — prefer the Article or Wikimedia tabs for news subjects."}
          </p>
          <div className="flex gap-2 mb-6">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search()}
              placeholder={source === "wikimedia" ? "JD Vance" : "iran protest"}
              dir="ltr"
              className="flex-1 px-3 py-2 text-[13px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
            />
            <button
              type="button"
              onClick={search}
              disabled={loading || !query.trim()}
              className="px-5 py-2 text-[13px] bg-blue-600 text-white disabled:opacity-50"
            >
              {loading ? "..." : "Search"}
            </button>
          </div>
        </>
      ) : (
        <p className="text-[13px] text-slate-500 mb-5 leading-6">
          Photos already collected from articles in this story. Picking one
          re-uploads it to R2 and pins it as the cover — independent of the
          original article so the cover survives if that article is removed.
        </p>
      )}

      {msg && (
        <p
          className="text-[13px] text-slate-600 dark:text-slate-400 mb-4"
          dir="ltr"
        >
          {msg}
        </p>
      )}

      {!loading && photos.length === 0 && source === "article" && articleImagesLoaded && (
        <p className="text-[13px] text-slate-500">
          No usable article images for this story. Try the Wikimedia or Unsplash
          tabs.
        </p>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {photos.map((p) => (
          <div
            key={p.id}
            className="border border-slate-200 dark:border-slate-800 overflow-hidden"
          >
            {/* Plain img on purpose — picker thumbs shouldn't go through Next's optimizer. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={p.regular_url}
              alt={p.alt || ""}
              className="w-full h-40 object-cover"
            />
            <div className="p-2">
              {source === "article" ? (
                <p className="text-[12px] text-slate-500 truncate" title={p.article_title_fa || ""}>
                  {p.article_title_fa || "(untitled article)"}
                </p>
              ) : (
                <p className="text-[12px] text-slate-500 truncate" dir="ltr">
                  by{" "}
                  <a
                    href={p.author_url || "#"}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-500"
                  >
                    {p.author_name || "unknown"}
                  </a>
                  {p.license && (
                    <span className="ml-1 text-slate-400">· {p.license}</span>
                  )}
                </p>
              )}
              <button
                type="button"
                onClick={() => pin(p)}
                disabled={pinning === p.id}
                className="mt-1 w-full px-2 py-1 text-[12px] bg-emerald-600 text-white disabled:opacity-50"
              >
                {pinning === p.id ? "Uploading..." : "Pick this image"}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
