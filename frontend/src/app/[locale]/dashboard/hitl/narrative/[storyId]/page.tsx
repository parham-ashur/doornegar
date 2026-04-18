"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { adminHeaders, hasAdminToken } from "../../_auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface NarrativeBullets {
  story_id: string;
  title_fa: string | null;
  bias_explanation_fa: string | null;
  principlist: string[];
  reformist: string[];
  moderate_diaspora: string[];
  radical_diaspora: string[];
}

// Join bullets with newlines for the textarea; split back on save.
const toText = (arr: string[]) => (arr || []).join("\n");
const fromText = (s: string) =>
  s.split("\n").map((l) => l.trim()).filter((l) => l.length > 0);

export default function NarrativeEditor() {
  const params = useParams<{ storyId: string }>();
  const storyId = params.storyId;
  const [authed, setAuthed] = useState(false);
  const [token, setToken] = useState("");
  const [data, setData] = useState<NarrativeBullets | null>(null);
  const [bias, setBias] = useState("");
  const [p, setP] = useState("");
  const [r, setR] = useState("");
  const [m, setM] = useState("");
  const [rad, setRad] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    setAuthed(hasAdminToken());
  }, []);

  useEffect(() => {
    if (!authed || !storyId) return;
    fetch(`${API}/api/v1/admin/hitl/stories/${storyId}/narrative`, {
      headers: adminHeaders(),
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((d: NarrativeBullets | null) => {
        if (!d) return;
        setData(d);
        setBias(d.bias_explanation_fa || "");
        setP(toText(d.principlist));
        setR(toText(d.reformist));
        setM(toText(d.moderate_diaspora));
        setRad(toText(d.radical_diaspora));
      });
  }, [authed, storyId]);

  const save = async () => {
    setSaving(true);
    setMsg("");
    const res = await fetch(`${API}/api/v1/admin/hitl/stories/${storyId}/narrative`, {
      method: "PATCH",
      headers: { ...adminHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({
        bias_explanation_fa: bias,
        principlist: fromText(p),
        reformist: fromText(r),
        moderate_diaspora: fromText(m),
        radical_diaspora: fromText(rad),
      }),
    });
    setSaving(false);
    setMsg(res.ok ? "ذخیره شد ✓" : "خطا در ذخیره");
  };

  if (!authed) {
    return (
      <div>
        <h1 className="text-xl font-black mb-4">ویرایش روایت</h1>
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

  if (!data) return <p className="text-[13px]">در حال بارگذاری...</p>;

  return (
    <div>
      <a href={`/fa/stories/${storyId}`} target="_blank" rel="noreferrer" className="text-[12px] text-blue-500 mb-2 block">
        ← مشاهدهٔ صفحهٔ خبر
      </a>
      <h1 className="text-xl font-black text-slate-900 dark:text-white mb-2">
        {data.title_fa}
      </h1>
      <p className="text-[13px] text-slate-500 mb-6 leading-6">
        هر بخش — یک بولت در هر خط (دو تا سه بولت در هر زیرگروه).
      </p>

      <div className="space-y-5">
        <div>
          <label className="block text-[13px] font-bold mb-1">
            تبیین سوگیری (bias_explanation_fa)
          </label>
          <textarea
            value={bias}
            onChange={(e) => setBias(e.target.value)}
            rows={3}
            className="w-full px-3 py-2 text-[13px] border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-[13px] font-bold mb-1 text-red-600">
              اصول‌گرا (داخل)
            </label>
            <textarea
              value={p}
              onChange={(e) => setP(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 text-[13px] border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
            />
          </div>
          <div>
            <label className="block text-[13px] font-bold mb-1 text-amber-600">
              اصلاح‌طلب (داخل)
            </label>
            <textarea
              value={r}
              onChange={(e) => setR(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 text-[13px] border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
            />
          </div>
          <div>
            <label className="block text-[13px] font-bold mb-1 text-blue-600">
              میانه‌رو (برون‌مرزی)
            </label>
            <textarea
              value={m}
              onChange={(e) => setM(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 text-[13px] border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
            />
          </div>
          <div>
            <label className="block text-[13px] font-bold mb-1 text-emerald-600">
              رادیکال (برون‌مرزی)
            </label>
            <textarea
              value={rad}
              onChange={(e) => setRad(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 text-[13px] border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
            />
          </div>
        </div>

        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="px-6 py-2 text-[13px] bg-blue-600 text-white disabled:opacity-50"
          >
            {saving ? "..." : "ذخیرهٔ روایت"}
          </button>
          {msg && <span className="text-[13px] text-emerald-600">{msg}</span>}
        </div>
      </div>
    </div>
  );
}
