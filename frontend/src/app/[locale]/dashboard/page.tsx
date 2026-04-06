"use client";

import { useLocale } from "next-intl";
import { useEffect, useState } from "react";
import {
  Activity, AlertCircle, CheckCircle, Clock, Database,
  Newspaper, RefreshCw, XCircle, Zap,
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

export default function DashboardPage() {
  const locale = useLocale();
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
      console.error("Failed to fetch dashboard data", e);
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
      alert(`Error: ${e.message}`);
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
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-900 dark:text-white">
            <Activity className="h-6 w-6 text-diaspora" />
            {locale === "fa" ? "داشبورد مانیتورینگ" : "Monitoring Dashboard"}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {locale === "fa" ? "وضعیت سیستم و مدیریت خطاها" : "System status and error management"}
          </p>
        </div>
        <button
          onClick={fetchData}
          className="flex items-center gap-2 rounded-lg bg-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-300 dark:bg-slate-700 dark:text-slate-300"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          {locale === "fa" ? "بروزرسانی" : "Refresh"}
        </button>
      </div>

      {/* Stats cards */}
      <div className="mb-8 grid gap-4 sm:grid-cols-4">
        <div className="card flex items-center gap-3">
          <div className="rounded-lg bg-emerald-100 p-2 dark:bg-emerald-900/30">
            <CheckCircle className="h-5 w-5 text-emerald-600" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900 dark:text-white">{successCount}</p>
            <p className="text-xs text-slate-500">{locale === "fa" ? "فید فعال" : "Active Feeds"}</p>
          </div>
        </div>
        <div className="card flex items-center gap-3">
          <div className="rounded-lg bg-red-100 p-2 dark:bg-red-900/30">
            <XCircle className="h-5 w-5 text-red-600" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900 dark:text-white">{errorCount}</p>
            <p className="text-xs text-slate-500">{locale === "fa" ? "فید خطادار" : "Failed Feeds"}</p>
          </div>
        </div>
        <div className="card flex items-center gap-3">
          <div className="rounded-lg bg-blue-100 p-2 dark:bg-blue-900/30">
            <Newspaper className="h-5 w-5 text-blue-600" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900 dark:text-white">{totalArticles}</p>
            <p className="text-xs text-slate-500">{locale === "fa" ? "مقاله جدید" : "New Articles"}</p>
          </div>
        </div>
        <div className="card flex items-center gap-3">
          <div className="rounded-lg bg-purple-100 p-2 dark:bg-purple-900/30">
            <Database className="h-5 w-5 text-purple-600" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900 dark:text-white">{stories.total || 0}</p>
            <p className="text-xs text-slate-500">{locale === "fa" ? "موضوع" : "Topics"}</p>
          </div>
        </div>
      </div>

      {/* Pipeline controls */}
      <div className="mb-8 card">
        <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white">
          {locale === "fa" ? "اجرای خط‌لوله" : "Run Pipeline"}
        </h2>
        <div className="flex flex-wrap gap-3">
          {[
            { key: "ingest", label: locale === "fa" ? "دریافت خبر" : "Ingest", icon: "📥" },
            { key: "nlp", label: locale === "fa" ? "پردازش NLP" : "NLP Process", icon: "🧠" },
            { key: "cluster", label: locale === "fa" ? "خوشه‌بندی" : "Cluster", icon: "🔗" },
            { key: "bias", label: locale === "fa" ? "تحلیل سوگیری" : "Bias Score", icon: "⚖️" },
          ].map(({ key, label, icon }) => (
            <button
              key={key}
              onClick={() => triggerPipeline(key)}
              disabled={running !== null}
              className="flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              <span>{icon}</span>
              {label}
              {running === key && <RefreshCw className="h-3 w-3 animate-spin" />}
            </button>
          ))}
        </div>
      </div>

      {/* Feed status table */}
      <div className="card overflow-x-auto">
        <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white">
          {locale === "fa" ? "وضعیت فیدها" : "Feed Status"}
        </h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-700">
              <th className="pb-2 pe-4 text-start">{locale === "fa" ? "رسانه" : "Source"}</th>
              <th className="pb-2 px-2 text-center">{locale === "fa" ? "وضعیت" : "Status"}</th>
              <th className="pb-2 px-2 text-center">{locale === "fa" ? "نوع" : "Type"}</th>
              <th className="pb-2 px-2 text-center">{locale === "fa" ? "یافته" : "Found"}</th>
              <th className="pb-2 px-2 text-center">{locale === "fa" ? "جدید" : "New"}</th>
              <th className="pb-2 ps-4 text-start">{locale === "fa" ? "خطا" : "Error"}</th>
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
                  className="border-b border-slate-100 dark:border-slate-800"
                >
                  <td className="py-2.5 pe-4 font-medium text-slate-800 dark:text-slate-200">
                    {locale === "fa" ? source.name_fa : source.name_en}
                  </td>
                  <td className="py-2.5 px-2 text-center">
                    {isSuccess && <CheckCircle className="mx-auto h-4 w-4 text-emerald-500" />}
                    {isError && <XCircle className="mx-auto h-4 w-4 text-red-500" />}
                    {!log && <Clock className="mx-auto h-4 w-4 text-slate-400" />}
                  </td>
                  <td className="py-2.5 px-2 text-center">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      source.state_alignment === "state" ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400" :
                      source.state_alignment === "semi_state" ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400" :
                      source.state_alignment === "independent" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400" :
                      "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400"
                    }`}>
                      {source.state_alignment}
                    </span>
                  </td>
                  <td className="py-2.5 px-2 text-center text-slate-600 dark:text-slate-400">
                    {log?.articles_found ?? "—"}
                  </td>
                  <td className="py-2.5 px-2 text-center text-slate-600 dark:text-slate-400">
                    {log?.articles_new ?? "—"}
                  </td>
                  <td className="py-2.5 ps-4 text-xs text-red-500 dark:text-red-400">
                    {log?.error_message
                      ? log.error_message.length > 60
                        ? log.error_message.slice(0, 60) + "…"
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
