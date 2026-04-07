"use client";

import { useEffect, useState } from "react";
import { MessageCircle, Eye, Share2, ExternalLink } from "lucide-react";

interface TelegramPost {
  id: string;
  channel_id: string;
  text: string | null;
  date: string;
  views: number;
  forwards: number;
  urls: string[];
}

interface SocialData {
  total_posts: number;
  posts: TelegramPost[];
}

export default function TelegramPanel({ storyId }: { storyId: string }) {
  const [data, setData] = useState<SocialData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    fetch(`${apiBase}/api/v1/social/stories/${storyId}/social`)
      .then((res) => res.ok ? res.json() : null)
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [storyId]);

  if (loading) return null;
  if (!data || data.total_posts === 0) return null;

  return (
    <div className="border-t border-slate-200 dark:border-slate-800 pt-6 mt-6" dir="rtl">
      <h3 className="text-base font-black text-slate-900 dark:text-white mb-4 pb-3 border-b border-slate-200 dark:border-slate-800 flex items-center gap-2">
        <MessageCircle className="h-4 w-4" />
        پوشش تلگرامی
        <span className="text-[11px] font-normal text-slate-400">{data.total_posts} پست</span>
      </h3>

      <div className="divide-y divide-slate-200 dark:divide-slate-800">
        {data.posts.slice(0, 10).map((post) => {
          // Clean text: remove markdown links, @mentions at end
          let text = post.text || "";
          text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1"); // [text](url) -> text
          text = text.replace(/@\w+\s*$/g, "").trim(); // remove trailing @channel

          return (
            <div key={post.id} className="py-4">
              <p className="text-sm text-slate-800 dark:text-slate-200 leading-7">
                {text.length > 300 ? text.slice(0, 300) + "..." : text}
              </p>
              <div className="mt-2 flex items-center gap-4 text-[11px] text-slate-400">
                {post.views > 0 && (
                  <span className="flex items-center gap-1">
                    <Eye className="h-3 w-3" />
                    {post.views.toLocaleString("fa-IR")} بازدید
                  </span>
                )}
                {post.forwards > 0 && (
                  <span className="flex items-center gap-1">
                    <Share2 className="h-3 w-3" />
                    {post.forwards.toLocaleString("fa-IR")} بازنشر
                  </span>
                )}
                {post.urls.length > 0 && (
                  <a
                    href={post.urls[0]}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    <ExternalLink className="h-3 w-3" />
                    منبع
                  </a>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
