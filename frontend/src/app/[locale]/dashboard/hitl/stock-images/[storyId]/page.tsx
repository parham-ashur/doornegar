"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { adminHeaders, hasAdminToken } from "../../_auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Photo {
  id: string;
  thumb_url: string;
  regular_url: string;
  raw_url: string;
  alt: string | null;
  author_name: string | null;
  author_url: string | null;
  unsplash_url: string | null;
  width: number;
  height: number;
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
// (dates, counts that Unsplash ignores), collapse whitespace, cap at 7 words
// so we don't over-constrain the query. Title_en from Niloofar tends to be
// an event sentence — the first clause is the richest search signal.
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
  const [query, setQuery] = useState("");
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [loading, setLoading] = useState(false);
  const [pinning, setPinning] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [story, setStory] = useState<StoryContext | null>(null);
  const [storyLoading, setStoryLoading] = useState(true);

  useEffect(() => {
    setAuthed(hasAdminToken());
  }, []);

  // Pull story context so the curator sees what they're choosing an
  // image FOR without tabbing back to the story page every time.
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
        // Prefill the search bar with English keywords extracted from the
        // story title so the first search is one-click instead of a manual
        // retype. Curator can edit before hitting جستجو.
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

  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setPhotos([]);
    try {
      const res = await fetch(
        `${API}/api/v1/admin/hitl/unsplash-search?q=${encodeURIComponent(query)}&per_page=9`,
        { headers: adminHeaders() }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setMsg(err.detail || "خطای جستجو");
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
      setMsg(`پین شد ✓  ${data.r2_url}`);
    } else {
      const err = await res.json().catch(() => ({}));
      setMsg(err.detail || "خطا");
    }
  };

  if (!authed) {
    return (
      <div>
        <h1 className="text-xl font-black mb-4">انتخاب تصویر</h1>
        <p className="text-[13px] mb-3">توکن ادمین:</p>
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
            ذخیره
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <a
        href={`/fa/stories/${storyId}`}
        target="_blank"
        rel="noreferrer"
        className="text-[12px] text-blue-500 mb-2 block"
      >
        ← صفحهٔ خبر
      </a>
      <h1 className="text-xl font-black text-slate-900 dark:text-white mb-4">
        انتخاب تصویر از Unsplash
      </h1>

      {/* Story context card — gives the curator the title, English
          translation, summary, and basic stats in one panel so they
          don't have to flip between tabs. */}
      {storyLoading && (
        <div className="mb-5 text-[12px] text-slate-400">در حال بارگذاری اطلاعات خبر…</div>
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
          <div className="text-[11px] text-slate-400">
            {story.source_count} رسانه · {story.article_count} مقاله
            {story.first_published_at && (
              <> · {new Date(story.first_published_at).toLocaleDateString("fa-IR")}</>
            )}
          </div>
        </div>
      )}

      <p className="text-[13px] text-slate-500 mb-3 leading-6">
        عبارت جستجو با واژه‌های انگلیسی عنوان خبر از پیش پر شد. می‌توانی قبل از جستجو تغییرش بدهی. Unsplash پرسش فارسی را ضعیف پوشش می‌دهد.
      </p>

      <div className="flex gap-2 mb-6">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
          placeholder="iran protest"
          dir="ltr"
          className="flex-1 px-3 py-2 text-[13px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
        />
        <button
          type="button"
          onClick={search}
          disabled={loading || !query.trim()}
          className="px-5 py-2 text-[13px] bg-blue-600 text-white disabled:opacity-50"
        >
          {loading ? "..." : "جستجو"}
        </button>
      </div>

      {msg && (
        <p
          className="text-[13px] text-slate-600 dark:text-slate-400 mb-4"
          dir="ltr"
        >
          {msg}
        </p>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {photos.map((p) => (
          <div
            key={p.id}
            className="border border-slate-200 dark:border-slate-800 overflow-hidden"
          >
            {/* Using plain img on purpose — we're displaying Unsplash preview
                thumbs, which we don't want run through Next's optimizer. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={p.regular_url}
              alt={p.alt || ""}
              className="w-full h-40 object-cover"
            />
            <div className="p-2">
              <p className="text-[12px] text-slate-500 truncate" dir="ltr">
                by{" "}
                <a
                  href={p.author_url || "#"}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-500"
                >
                  {p.author_name}
                </a>
              </p>
              <button
                type="button"
                onClick={() => pin(p)}
                disabled={pinning === p.id}
                className="mt-1 w-full px-2 py-1 text-[12px] bg-emerald-600 text-white disabled:opacity-50"
              >
                {pinning === p.id ? "در حال آپلود..." : "انتخاب این تصویر"}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
