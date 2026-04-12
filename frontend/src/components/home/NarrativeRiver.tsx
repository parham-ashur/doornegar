import type { StoryBrief } from "@/lib/types";

function getDailyCoverage(stories: StoryBrief[]): { label: string; conservative: number; opposition: number }[] {
  const now = new Date();
  const days: { label: string; conservative: number; opposition: number }[] = [];

  for (let d = 6; d >= 0; d--) {
    const date = new Date(now);
    date.setDate(date.getDate() - d);
    const dateStr = date.toISOString().slice(0, 10);
    const label = d === 0 ? "امروز" : d === 1 ? "دیروز" : `${d} روز`;

    let conservative = 0;
    let opposition = 0;
    for (const s of stories) {
      if (!s.first_published_at) continue;
      const pubDate = s.first_published_at.slice(0, 10);
      if (pubDate === dateStr) {
        conservative += Math.round(s.article_count * (s.state_pct || 0) / 100);
        opposition += Math.round(s.article_count * (s.diaspora_pct || 0) / 100);
      }
    }
    days.push({ label, conservative, opposition });
  }
  return days;
}

export default function NarrativeRiver({ stories }: { stories: StoryBrief[]; locale?: string }) {
  const days = getDailyCoverage(stories);
  const maxTotal = Math.max(...days.map(d => d.conservative + d.opposition), 1);

  return (
    <div dir="rtl">
      <div className="flex items-end gap-2" style={{ height: 140 }}>
        {days.map((day, i) => {
          const cHeight = (day.conservative / maxTotal) * 120;
          const oHeight = (day.opposition / maxTotal) * 120;
          const total = day.conservative + day.opposition;
          return (
            <div key={i} className="flex-1 flex flex-col items-center gap-0">
              {/* Stacked bar */}
              <div className="w-full flex flex-col items-stretch justify-end" style={{ height: 120 }}>
                {cHeight > 0 && (
                  <div className="bg-[#1e3a5f] dark:bg-blue-800/80 transition-all" style={{ height: cHeight }} />
                )}
                {oHeight > 0 && (
                  <div className="bg-[#ea580c] dark:bg-orange-700/80 transition-all" style={{ height: oHeight }} />
                )}
              </div>
              {/* Day label */}
              <span className="text-[10px] text-slate-400 mt-1.5">{day.label}</span>
              {/* Count */}
              {total > 0 && <span className="text-[9px] text-slate-300 dark:text-slate-600">{total}</span>}
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center justify-center gap-5 mt-3 text-[11px] text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 bg-[#1e3a5f] dark:bg-blue-800/80 inline-block" />
          محافظه‌کار
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 bg-[#ea580c] dark:bg-orange-700/80 inline-block" />
          اپوزیسیون
        </span>
      </div>
    </div>
  );
}
