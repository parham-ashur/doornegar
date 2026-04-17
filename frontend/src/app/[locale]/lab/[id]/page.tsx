import { setRequestLocale } from "next-intl/server";
import Link from "next/link";
import type { TopicDetail, DebatePosition, AnalystPerspective } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchTopic(id: string): Promise<TopicDetail | null> {
  try {
    const res = await fetch(`${API}/api/v1/lab/topics/${id}`, { next: { revalidate: 30 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

function StrengthBar({ strength }: { strength: number }) {
  return (
    <div className="flex gap-0.5 mt-1">
      {[1, 2, 3, 4, 5].map((i) => (
        <div
          key={i}
          className={`h-1.5 w-4 ${
            i <= strength
              ? "bg-slate-700 dark:bg-slate-300"
              : "bg-slate-200 dark:bg-slate-700"
          }`}
        />
      ))}
    </div>
  );
}

function DebateView({ analysis }: { analysis: TopicDetail["analysis"] }) {
  if (!analysis) return null;
  const positions = analysis.positions || [];
  const disagreements = analysis.key_disagreements_fa || [];

  return (
    <div className="space-y-8">
      {/* Summary */}
      {analysis.topic_summary_fa && (
        <div>
          <h3 className="text-sm font-black text-slate-900 dark:text-white mb-2">خلاصه بحث</h3>
          <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">{analysis.topic_summary_fa}</p>
        </div>
      )}

      {/* Positions */}
      {positions.length > 0 && (
        <div>
          <h3 className="text-sm font-black text-slate-900 dark:text-white mb-4">مواضع</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {positions.map((pos: DebatePosition, i: number) => (
              <div key={i} className="border border-slate-200 dark:border-slate-800 p-4">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-[14px] font-bold text-slate-900 dark:text-white">{pos.position_fa}</h4>
                  <StrengthBar strength={pos.strength} />
                </div>
                <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">{pos.argument_fa}</p>
                {pos.supporting_sources.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1">
                    {pos.supporting_sources.map((src, j) => (
                      <span key={j} className="px-2 py-0.5 text-[10px] border border-slate-300 dark:border-slate-700 text-slate-500 dark:text-slate-400">
                        {src}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Key Disagreements */}
      {disagreements.length > 0 && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-6">
          <h3 className="text-sm font-black text-slate-900 dark:text-white mb-3">نقاط اختلاف</h3>
          <ul className="space-y-2">
            {disagreements.map((d, i) => (
              <li key={i} className="flex items-start gap-2 text-[13px] leading-6 text-slate-600 dark:text-slate-400">
                <span className="text-amber-500 mt-1 shrink-0">●</span>
                {d}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Conclusion */}
      {analysis.conclusion_fa && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-6">
          <h3 className="text-sm font-black text-slate-900 dark:text-white mb-2">جمع‌بندی</h3>
          <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">{analysis.conclusion_fa}</p>
        </div>
      )}
    </div>
  );
}

function NewsView({ analysis }: { analysis: TopicDetail["analysis"] }) {
  if (!analysis) return null;

  return (
    <div className="space-y-6">
      {/* Summary */}
      {analysis.summary_fa && (
        <div>
          <h3 className="text-sm font-black text-slate-900 dark:text-white mb-2">خلاصه</h3>
          <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">{analysis.summary_fa}</p>
        </div>
      )}

      {/* Per-side analysis */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {analysis.state_summary_fa && (
          <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
            <h4 className="text-xs font-bold mb-2 text-red-600 dark:text-red-400">دیدگاه درون‌مرزی</h4>
            <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">{analysis.state_summary_fa}</p>
            {analysis.scores?.state?.framing && (
              <div className="mt-3 flex items-center gap-1.5 flex-wrap text-[11px]">
                <span className="text-slate-500">چارچوب‌بندی:</span>
                {(Array.isArray(analysis.scores.state.framing) ? analysis.scores.state.framing : [analysis.scores.state.framing]).map((f, i) => (
                  <span key={i} className="px-2 py-0.5 border border-slate-300 dark:border-slate-700 font-medium text-slate-700 dark:text-slate-300">{f}</span>
                ))}
              </div>
            )}
          </div>
        )}
        {analysis.independent_summary_fa && (
          <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
            <h4 className="text-xs font-bold mb-2 text-emerald-600 dark:text-emerald-400">دیدگاه مستقل</h4>
            <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">{analysis.independent_summary_fa}</p>
            {analysis.scores?.independent?.framing && (
              <div className="mt-3 flex items-center gap-1.5 flex-wrap text-[11px]">
                <span className="text-slate-500">چارچوب‌بندی:</span>
                {(Array.isArray(analysis.scores.independent.framing) ? analysis.scores.independent.framing : [analysis.scores.independent.framing]).map((f, i) => (
                  <span key={i} className="px-2 py-0.5 border border-slate-300 dark:border-slate-700 font-medium text-slate-700 dark:text-slate-300">{f}</span>
                ))}
              </div>
            )}
          </div>
        )}
        {analysis.diaspora_summary_fa && (
          <div className="border-t border-slate-200 dark:border-slate-800 pt-4">
            <h4 className="text-xs font-bold mb-2 text-blue-600 dark:text-blue-400">دیدگاه برون‌مرزی</h4>
            <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-400">{analysis.diaspora_summary_fa}</p>
            {analysis.scores?.diaspora?.framing && (
              <div className="mt-3 flex items-center gap-1.5 flex-wrap text-[11px]">
                <span className="text-slate-500">چارچوب‌بندی:</span>
                {(Array.isArray(analysis.scores.diaspora.framing) ? analysis.scores.diaspora.framing : [analysis.scores.diaspora.framing]).map((f, i) => (
                  <span key={i} className="px-2 py-0.5 border border-slate-300 dark:border-slate-700 font-medium text-slate-700 dark:text-slate-300">{f}</span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bias comparison */}
      {analysis.bias_explanation_fa && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-6">
          <h3 className="text-sm font-black text-slate-900 dark:text-white mb-2">مقایسه سوگیری</h3>
          <p className="text-[13px] leading-7 text-slate-600 dark:text-slate-400">{analysis.bias_explanation_fa}</p>
        </div>
      )}
    </div>
  );
}

export default async function TopicDetailPage({
  params: { locale, id },
}: {
  params: { locale: string; id: string };
}) {
  setRequestLocale(locale);
  const topic = await fetchTopic(id);

  if (!topic) {
    return (
      <div dir="rtl" className="mx-auto max-w-7xl px-6 py-20 text-center">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">موضوع پیدا نشد</h2>
      </div>
    );
  }

  return (
    <div dir="rtl" className="mx-auto max-w-7xl px-6 lg:px-8 py-8">
      {/* Breadcrumb */}
      <div className="text-[12px] text-slate-400 mb-4">
        <Link href={`/${locale}/lab`} className="hover:text-blue-600">آزمایشگاه</Link>
        <span className="mx-1">/</span>
        <span>{topic.title_fa}</span>
      </div>

      {/* Header */}
      <div className="border-b border-slate-200 dark:border-slate-800 pb-6 mb-8">
        <div className="flex items-center gap-3 mb-3">
          <span className={`px-2.5 py-1 text-[12px] font-bold border ${
            topic.mode === "debate"
              ? "border-amber-400 text-amber-600 dark:text-amber-400"
              : "border-blue-400 text-blue-600 dark:text-blue-400"
          }`}>
            {topic.mode === "debate" ? "بحث" : "خبر"}
          </span>
          <span className="text-[11px] text-slate-400">{topic.article_count} مقاله مرتبط</span>
          {topic.analyzed_at && (
            <span className="text-[11px] text-emerald-500">تحلیل‌شده</span>
          )}
        </div>
        <h1 className="text-[28px] font-black leading-snug text-slate-900 dark:text-white">
          {topic.title_fa}
        </h1>
        {topic.description_fa && (
          <p className="mt-2 text-[14px] text-slate-500 dark:text-slate-400">{topic.description_fa}</p>
        )}
      </div>

      {/* Analysis */}
      {topic.analysis ? (
        <div className="mb-10">
          {topic.mode === "debate" ? (
            <DebateView analysis={topic.analysis} />
          ) : (
            <NewsView analysis={topic.analysis} />
          )}
        </div>
      ) : (
        <div className="text-center py-12 border border-dashed border-slate-300 dark:border-slate-700 mb-10">
          <p className="text-sm text-slate-500">هنوز تحلیلی ایجاد نشده</p>
          <p className="text-[12px] text-slate-400 mt-1">ابتدا مقالات را مطابقت دهید، سپس تحلیل را اجرا کنید</p>
        </div>
      )}

      {/* Analyst Perspectives */}
      {topic.analysts && topic.analysts.length > 0 && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-8 mb-8">
          <h3 className="text-sm font-black text-slate-900 dark:text-white mb-5">تحلیلگران ({topic.analysts.length})</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {topic.analysts.map((analyst: AnalystPerspective, i: number) => {
              const leaningColor: Record<string, string> = {
                pro_regime: "border-red-400 text-red-600 dark:text-red-400",
                reformist: "border-amber-400 text-amber-600 dark:text-amber-400",
                opposition: "border-blue-400 text-blue-600 dark:text-blue-400",
                monarchist: "border-purple-400 text-purple-600 dark:text-purple-400",
                neutral: "border-emerald-400 text-emerald-600 dark:text-emerald-400",
              };
              const leaningLabel: Record<string, string> = {
                pro_regime: "درون‌مرزی",
                reformist: "اصلاح‌طلب",
                opposition: "برون‌مرزی",
                monarchist: "سلطنت‌طلب",
                neutral: "مستقل",
              };
              const color = leaningColor[analyst.political_leaning] || leaningColor.neutral;
              const label = leaningLabel[analyst.political_leaning] || "مستقل";

              return (
                <div key={i} className="border border-slate-200 dark:border-slate-800 p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 bg-slate-200 dark:bg-slate-700 flex items-center justify-center text-[11px] font-bold text-slate-500 dark:text-slate-400">
                        {analyst.name_fa.charAt(0)}
                      </div>
                      <div>
                        <p className="text-[13px] font-bold text-slate-900 dark:text-white">{analyst.name_fa}</p>
                        <p className="text-[10px] text-slate-400">{analyst.platform} · {analyst.followers}</p>
                      </div>
                    </div>
                    <span className={`px-1.5 py-0.5 text-[9px] font-bold border ${color}`}>
                      {label}
                    </span>
                  </div>
                  <p className="text-[12px] leading-5 text-slate-600 dark:text-slate-400">
                    «{analyst.quote_fa}»
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Matched Articles */}
      {topic.articles.length > 0 && (
        <div className="border-t border-slate-200 dark:border-slate-800 pt-8">
          <h3 className="text-sm font-black text-slate-900 dark:text-white mb-4">
            مقالات مرتبط ({topic.articles.length})
          </h3>
          <div className="space-y-0">
            {topic.articles.map((art) => (
              <div key={art.id} className="py-3 border-b border-slate-100 dark:border-slate-800/50">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-[13px] font-bold text-slate-900 dark:text-white truncate">
                      {art.title_fa || art.title_en || "بدون عنوان"}
                    </p>
                    <p className="mt-0.5 text-[11px] text-slate-400">
                      {art.source_name_fa || "نامشخص"}
                      {art.source_state_alignment && (
                        <span className={`mr-2 ${
                          art.source_state_alignment === "state" || art.source_state_alignment === "semi_state"
                            ? "text-red-500"
                            : art.source_state_alignment === "diaspora"
                            ? "text-blue-500"
                            : "text-emerald-500"
                        }`}>
                          {art.source_state_alignment === "state" ? "درون‌مرزی"
                            : art.source_state_alignment === "semi_state" ? "نیمه‌درون‌مرزی"
                            : art.source_state_alignment === "diaspora" ? "برون‌مرزی"
                            : "مستقل"}
                        </span>
                      )}
                    </p>
                  </div>
                  {art.match_confidence !== null && (
                    <span className="text-[10px] text-slate-400 whitespace-nowrap">
                      {Math.round(art.match_confidence * 100)}٪
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
