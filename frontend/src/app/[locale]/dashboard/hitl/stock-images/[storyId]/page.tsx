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

  useEffect(() => {
    setAuthed(hasAdminToken());
  }, []);

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
      <a href={`/fa/stories/${storyId}`} target="_blank" rel="noreferrer" className="text-[12px] text-blue-500 mb-2 block">
        ← صفحهٔ خبر
      </a>
      <h1 className="text-xl font-black text-slate-900 dark:text-white mb-2">
        انتخاب تصویر از Unsplash
      </h1>
      <p className="text-[13px] text-slate-500 mb-4 leading-6">
        کلمه‌ای انگلیسی مرتبط با خبر وارد کنید (Unsplash فعلاً پرسش فارسی را ضعیف پوشش می‌دهد).
        نمونه: «iran protest», «strait of hormuz», «lebanon damage».
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
        <p className="text-[13px] text-slate-600 dark:text-slate-400 mb-4" dir="ltr">
          {msg}
        </p>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {photos.map((p) => (
          <div key={p.id} className="border border-slate-200 dark:border-slate-800 overflow-hidden">
            {/* Using plain img on purpose — we're displaying Unsplash preview
                thumbs, which we don't want run through Next's optimizer. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={p.regular_url} alt={p.alt || ""} className="w-full h-40 object-cover" />
            <div className="p-2">
              <p className="text-[12px] text-slate-500 truncate" dir="ltr">
                by{" "}
                <a href={p.author_url || "#"} target="_blank" rel="noreferrer" className="text-blue-500">
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
