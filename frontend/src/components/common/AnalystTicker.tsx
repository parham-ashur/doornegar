"use client";

import { useEffect, useState } from "react";
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AnalystQuote {
  name_fa: string;
  political_leaning: string;
  followers: string;
  quote_fa: string;
  topic_fa: string;
}

export default function AnalystTicker() {
  const [quotes, setQuotes] = useState<AnalystQuote[]>([]);
  const [current, setCurrent] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (quotes.length > 0) return; // Already loaded
    let cancelled = false;

    (async () => {
      try {
        const res = await fetch(`${API}/api/v1/lab/topics?page_size=10`);
        const data = await res.json();
        const topics = (data.topics || []).filter((t: any) => t.has_analysts);

        // Fetch all topic details in parallel
        const details = await Promise.all(
          topics.map((t: any) => fetch(`${API}/api/v1/lab/topics/${t.id}`).then((r) => r.json()).catch(() => null))
        );

        if (cancelled) return;

        const allQuotes: AnalystQuote[] = [];
        details.forEach((detail, i) => {
          if (!detail) return;
          for (const a of detail.analysts || []) {
            allQuotes.push({
              name_fa: a.name_fa,
              political_leaning: a.political_leaning,
              followers: a.followers,
              quote_fa: a.quote_fa,
              topic_fa: topics[i].title_fa,
            });
          }
        });

        // Shuffle
        for (let i = allQuotes.length - 1; i > 0; i--) {
          const j = Math.floor(Math.random() * (i + 1));
          [allQuotes[i], allQuotes[j]] = [allQuotes[j], allQuotes[i]];
        }
        setQuotes(allQuotes);
      } catch {}
    })();

    return () => { cancelled = true; };
  }, [quotes.length]);

  // Rotate every 8 seconds with fade transition
  useEffect(() => {
    if (quotes.length <= 1) return;
    const interval = setInterval(() => {
      setVisible(false);
      setTimeout(() => {
        setCurrent((c) => (c + 1) % quotes.length);
        setVisible(true);
      }, 500); // fade out duration
    }, 8000);
    return () => clearInterval(interval);
  }, [quotes.length]);

  if (quotes.length === 0) return null;

  const q = quotes[current];

  return (
    <div className="mt-4 border-t border-slate-200/50 dark:border-slate-800/50 pt-3 h-[72px] overflow-hidden">
      <div
        className={`transition-opacity duration-500 ${visible ? "opacity-100" : "opacity-0"}`}
      >
        <p className="text-[11px] leading-5 text-slate-400 dark:text-slate-500 italic line-clamp-2">
          «{q.quote_fa}»
        </p>
        <div className="mt-1.5 flex items-center gap-2 text-[10px]">
          <span className="font-bold text-slate-500 dark:text-slate-400">{q.name_fa}</span>
          <span className="text-slate-400/60">{q.followers}</span>
        </div>
      </div>
    </div>
  );
}
