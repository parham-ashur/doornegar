"use client";

import { useEffect, useState } from "react";
import {
  Activity, CheckCircle, Clock,
  Database, Newspaper, RefreshCw, XCircle,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface IngestionLog {
  id: string;
  source_id: string;
  feed_url: string;
  status: string;
  articles_found: number;
  articles_new: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

const alignmentLabels: Record<string, string> = {
  state: "حکومتی",
  semi_state: "نیمه‌دولتی",
  independent: "مستقل",
  diaspora: "برون‌مرزی",
};

export default function DashboardPage() {
  const [logs, setLogs] = useState<IngestionLog[]>([]);
  const [sources, setSources] = useState<any[]>([]);
  const [stories, setStories] = useState<any>({ total: 0 });
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState<string | null>(null);

  async function fetchData() {
    setLoading(true);
    try {
      const [logRes, srcRes, storyRes] = await Promise.all([
        fetch(`${API}/api/v1/admin/ingest/log?limit=20`).then((r) => r.json()),
        fetch(`${API}/api/v1/sources`).then((r) => r.json()),
        fetch(`${API}/api/v1/stories?page_size=1`).then((r) => r.json()),
      ]);
      setLogs(logRes.logs || []);
      setSources(srcRes.sources || []);
      setStories(storyRes);
    } catch (e) {
      console.error("خطا در دریافت اطلاعات داشبورد", e);
    }
    setLoading(false);
  }

  useEffect(() => {
    fetchData();
  }, []);

  async function triggerPipeline(step: string) {
    setRunning(step);
    try {
      const res = await fetch(`${API}/api/v1/admin/${step}/trigger`, { method: "POST" });
      const data = await res.json();
      alert(JSON.stringify(data, null, 2));
      fetchData();
    } catch (e: any) {
      alert(`خطا: ${e.message}`);
    }
    setRunning(null);
  }

  // Group logs by source
  const sourceMap = new Map(sources.map((s: any) => [s.id, s]));
  const latestBySource = new Map<string, IngestionLog>();
  logs.forEach((log) => {
    if (!latestBySource.has(log.source_id)) {
      latestBySource.set(log.source_id, log);
    }
  });

  const successCount = Array.from(latestBySource.values()).filter((l) => l.status === "success").length;
  const errorCount = Array.from(latestBySource.values()).filter((l) => l.status === "error").length;
  const totalArticles = logs.reduce((sum, l) => sum + l.articles_new, 0);

  return (
    <div dir="rtl" className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
            <Activity className="h-6 w-6 text-blue-400" />
            داشبورد مانیتورینگ
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            وضعیت سیستم و مدیریت خطاها
          </p>
        </div>
        <button
          onClick={fetchData}
          className="flex items-center gap-2 rounded-lg bg-slate-900/80 ring-1 ring-white/[0.06] px-4 py-2 text-sm font-medium text-slate-300 hover:ring-white/10 transition-colors"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          بروزرسانی
        </button>
      </div>

      {/* Stats cards */}
      <div className="mb-8 grid gap-4 sm:grid-cols-4">
        <div className="bg-slate-900/80 ring-1 ring-white/[0.06] rounded-2xl p-5 flex items-center gap-3">
          <div className="rounded-lg bg-emerald-500/20 p-2">
            <CheckCircle className="h-5 w-5 text-emerald-400" />
          </div>
          <div>
            <p className="text-2xl font-bold text-white">{successCount}</p>
            <p className="text-xs text-slate-400">فیدهای فعال</p>
          </div>
        </div>
        <div className="bg-slate-900/80 ring-1 ring-white/[0.06] rounded-2xl p-5 flex items-center gap-3">
          <div className="rounded-lg bg-red-500/20 p-2">
            <XCircle className="h-5 w-5 text-red-400" />
          </div>
          <div>
            <p className="text-2xl font-bold text-white">{errorCount}</p>
            <p className="text-xs text-slate-400">خطا</p>
          </div>
        </div>
        <div className="bg-slate-900/80 ring-1 ring-white/[0.06] rounded-2xl p-5 flex items-center gap-3">
          <div className="rounded-lg bg-blue-500/20 p-2">
            <Newspaper className="h-5 w-5 text-blue-400" />
          </div>
          <div>
            <p className="text-2xl font-bold text-white">{totalArticles}</p>
            <p className="text-xs text-slate-400">مقالات جدید</p>
          </div>
        </div>
        <div className="bg-slate-900/80 ring-1 ring-white/[0.06] rounded-2xl p-5 flex items-center gap-3">
          <div className="rounded-lg bg-purple-500/20 p-2">
            <Database className="h-5 w-5 text-purple-400" />
          </div>
          <div>
            <p className="text-2xl font-bold text-white">{stories.total || 0}</p>
            <p className="text-xs text-slate-400">موضوعات</p>
          </div>
        </div>
      </div>

      {/* Pipeline controls */}
      <div className="mb-8 bg-slate-900/80 ring-1 ring-white/[0.06] rounded-2xl p-5">
        <h2 className="mb-4 text-sm font-semibold text-white">
          اجرای خط‌لوله
        </h2>
        <div className="flex flex-wrap gap-3">
          {[
            { key: "ingest", label: "دریافت خبر" },
            { key: "nlp", label: "پردازش NLP" },
            { key: "cluster", label: "خوشه‌بندی" },
            { key: "bias", label: "امتیاز سوگیری" },
          ].map(({ key, label }) => (
            <button
              key={key}
              onClick={() => triggerPipeline(key)}
              disabled={running !== null}
              className="flex items-center gap-2 rounded-lg ring-1 ring-white/[0.06] bg-slate-800 px-4 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-700 hover:ring-white/10 disabled:opacity-50"
            >
              {label}
              {running === key && <RefreshCw className="h-3 w-3 animate-spin" />}
            </button>
          ))}
        </div>
      </div>

      {/* Feed status table */}
      <div className="bg-slate-900/80 ring-1 ring-white/[0.06] rounded-2xl p-5 overflow-x-auto">
        <h2 className="mb-4 text-sm font-semibold text-white">
          وضعیت فیدها
        </h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/[0.06] text-xs text-slate-400">
              <th className="pb-2 pe-4 text-start">رسانه</th>
              <th className="pb-2 px-2 text-center">وضعیت</th>
              <th className="pb-2 px-2 text-center">نوع</th>
              <th className="pb-2 px-2 text-center">یافته</th>
              <th className="pb-2 px-2 text-center">جدید</th>
              <th className="pb-2 ps-4 text-start">خطا</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((source: any) => {
              const log = latestBySource.get(source.id);
              const isSuccess = log?.status === "success";
              const isError = log?.status === "error";

              return (
                <tr
                  key={source.id}
                  className="border-b border-white/[0.04]"
                >
                  <td className="py-2.5 pe-4 font-medium text-slate-200">
                    {source.name_fa}
                  </td>
                  <td className="py-2.5 px-2 text-center">
                    {isSuccess && <CheckCircle className="mx-auto h-4 w-4 text-emerald-400" />}
                    {isError && <XCircle className="mx-auto h-4 w-4 text-red-400" />}
                    {!log && <Clock className="mx-auto h-4 w-4 text-slate-500" />}
                  </td>
                  <td className="py-2.5 px-2 text-center">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      source.state_alignment === "state" ? "bg-red-500/20 text-red-400 ring-1 ring-red-500/30" :
                      source.state_alignment === "semi_state" ? "bg-amber-500/20 text-amber-400 ring-1 ring-amber-500/30" :
                      source.state_alignment === "independent" ? "bg-emerald-500/20 text-emerald-400 ring-1 ring-emerald-500/30" :
                      "bg-blue-500/20 text-blue-400 ring-1 ring-blue-500/30"
                    }`}>
                      {alignmentLabels[source.state_alignment] || source.state_alignment}
                    </span>
                  </td>
                  <td className="py-2.5 px-2 text-center text-slate-400">
                    {log?.articles_found ?? "—"}
                  </td>
                  <td className="py-2.5 px-2 text-center text-slate-400">
                    {log?.articles_new ?? "—"}
                  </td>
                  <td className="py-2.5 ps-4 text-xs text-red-400">
                    {log?.error_message
                      ? log.error_message.length > 60
                        ? log.error_message.slice(0, 60) + "..."
                        : log.error_message
                      : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
