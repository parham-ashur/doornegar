"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { adminHeaders, hasAdminToken } from "../_auth";
import { narrativeGroupOfSource, GROUP_COLORS, GROUP_LABELS_EN } from "@/lib/narrativeGroups";
import OutletTabs from "@/components/dashboard/OutletTabs";
import type { Source } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Faction = "hardline" | "principlist" | "reformist" | "opposition" | "monarchist" | "radical" | "";
type Alignment = "state" | "semi_state" | "independent" | "diaspora";
type Location = "inside_iran" | "outside_iran";

interface Draft {
  state_alignment: Alignment;
  production_location: Location;
  factional_alignment: Faction;
  irgc_affiliated: boolean;
  is_active: boolean;
}

function sourceToDraft(s: Source): Draft {
  return {
    state_alignment: (s.state_alignment as Alignment) || "independent",
    production_location: (s.production_location as Location) || "inside_iran",
    factional_alignment: (s.factional_alignment as Faction) || "",
    irgc_affiliated: Boolean(s.irgc_affiliated),
    is_active: Boolean(s.is_active),
  };
}

function isDirty(a: Draft, b: Draft): boolean {
  return (
    a.state_alignment !== b.state_alignment ||
    a.production_location !== b.production_location ||
    a.factional_alignment !== b.factional_alignment ||
    a.irgc_affiliated !== b.irgc_affiliated ||
    a.is_active !== b.is_active
  );
}

export default function SourcesHitlPage() {
  const [authed, setAuthed] = useState(false);
  const [sources, setSources] = useState<Source[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [status, setStatus] = useState<Record<string, "saved" | "error">>({});

  useEffect(() => {
    setAuthed(hasAdminToken());
  }, []);

  const load = async () => {
    const res = await fetch(`${API}/api/v1/sources?limit=100`);
    if (!res.ok) return;
    const data = await res.json();
    const list: Source[] = Array.isArray(data) ? data : data.sources;
    list.sort((a, b) => a.slug.localeCompare(b.slug));
    setSources(list);
    const d: Record<string, Draft> = {};
    list.forEach((s) => {
      d[s.slug] = sourceToDraft(s);
    });
    setDrafts(d);
  };

  useEffect(() => {
    if (authed) load();
  }, [authed]);

  const save = async (slug: string) => {
    const draft = drafts[slug];
    if (!draft) return;
    setSaving(slug);
    setStatus((p) => {
      const { [slug]: _, ...rest } = p;
      return rest;
    });
    try {
      const body: Record<string, unknown> = {
        state_alignment: draft.state_alignment,
        production_location: draft.production_location,
        factional_alignment: draft.factional_alignment || null,
        irgc_affiliated: draft.irgc_affiliated,
        is_active: draft.is_active,
      };
      const res = await fetch(`${API}/api/v1/admin/sources/${slug}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...adminHeaders() },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(String(res.status));
      setStatus((p) => ({ ...p, [slug]: "saved" }));
      // Refresh local copy so isDirty goes quiet
      if (sources) {
        const updated = sources.map((s) =>
          s.slug === slug
            ? {
                ...s,
                state_alignment: draft.state_alignment,
                production_location: draft.production_location,
                factional_alignment: draft.factional_alignment || null,
                irgc_affiliated: draft.irgc_affiliated,
                is_active: draft.is_active,
              }
            : s,
        );
        setSources(updated);
      }
      setTimeout(() => {
        setStatus((p) => {
          const { [slug]: _, ...rest } = p;
          return rest;
        });
      }, 2000);
    } catch {
      setStatus((p) => ({ ...p, [slug]: "error" }));
    } finally {
      setSaving(null);
    }
  };

  const grouped = useMemo(() => {
    if (!sources) return null;
    const g: Record<string, Source[]> = {
      principlist: [],
      reformist: [],
      moderate_diaspora: [],
      radical_diaspora: [],
    };
    for (const s of sources) {
      g[narrativeGroupOfSource(s)].push(s);
    }
    return g;
  }, [sources]);

  if (!authed) {
    return (
      <div className="p-6">
        <p className="text-sm text-slate-500">
          Sign in from the{" "}
          <Link href="/fa/dashboard" className="text-blue-600 hover:underline">
            dashboard
          </Link>{" "}
          first to access this page.
        </p>
      </div>
    );
  }

  if (!sources) {
    return (
      <div className="p-6 text-[13px] text-slate-400">Loading…</div>
    );
  }

  return (
    <div>
      <OutletTabs active="sources" />
      <div className="mb-6">
        <h1 className="text-xl font-black text-slate-900 dark:text-white">
          Source classification
        </h1>
        <p className="text-[13px] text-slate-500 dark:text-slate-400 mt-1 leading-6">
          Each outlet's narrative subgroup (principlist / reformist / moderate
          diaspora / radical diaspora) is derived from three fields: production
          location (inside / outside Iran), state alignment, and political
          faction. Fix wrong classifications here — changes propagate to every
          page immediately.
        </p>
      </div>

      {/* Summary by group */}
      {grouped && (
        <div className="mb-6 grid grid-cols-2 md:grid-cols-4 gap-3">
          {(["principlist", "reformist", "moderate_diaspora", "radical_diaspora"] as const).map((g) => (
            <div key={g} className="border border-slate-200 dark:border-slate-800 p-3">
              <div className="flex items-center gap-2 mb-1">
                <span
                  className="inline-block w-2 h-2"
                  style={{ backgroundColor: GROUP_COLORS[g] }}
                />
                <span className="text-[12px] font-bold" style={{ color: GROUP_COLORS[g] }}>
                  {GROUP_LABELS_EN[g]}
                </span>
              </div>
              <p className="text-[13px] text-slate-500 dark:text-slate-400 leading-6">
                {grouped[g].length} source{grouped[g].length === 1 ? "" : "s"}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Source list */}
      <div className="border border-slate-200 dark:border-slate-800">
        {sources.map((s) => {
          const draft = drafts[s.slug];
          const original = sourceToDraft(s);
          const dirty = draft && isDirty(draft, original);
          const group = narrativeGroupOfSource(s);
          const saveStatus = status[s.slug];
          return (
            <div
              key={s.slug}
              className="flex flex-col md:flex-row md:items-center gap-3 p-3 border-b border-slate-100 dark:border-slate-800/60 last:border-b-0"
            >
              {/* Source identity */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className="inline-block w-2 h-2 shrink-0"
                    style={{ backgroundColor: GROUP_COLORS[group] }}
                  />
                  <span className="text-[14px] font-bold text-slate-900 dark:text-white truncate">
                    {s.name_fa || s.slug}
                  </span>
                  <span className="text-[11px] text-slate-400 font-mono">{s.slug}</span>
                </div>
                <p className="text-[11px] text-slate-400 mt-0.5 font-mono truncate" dir="ltr">
                  {s.website_url || "—"}
                </p>
                <p className="text-[11px] mt-0.5" style={{ color: GROUP_COLORS[group] }}>
                  Subgroup: {GROUP_LABELS_EN[group]}
                </p>
              </div>

              {/* Classification selects */}
              {draft && (
                <div className="flex flex-wrap items-center gap-2 shrink-0">
                  <select
                    value={draft.production_location}
                    onChange={(e) =>
                      setDrafts((p) => ({
                        ...p,
                        [s.slug]: { ...draft, production_location: e.target.value as Location },
                      }))
                    }
                    className="text-[12px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-1"
                  >
                    <option value="inside_iran">Inside Iran</option>
                    <option value="outside_iran">Outside Iran</option>
                  </select>

                  <select
                    value={draft.state_alignment}
                    onChange={(e) =>
                      setDrafts((p) => ({
                        ...p,
                        [s.slug]: { ...draft, state_alignment: e.target.value as Alignment },
                      }))
                    }
                    className="text-[12px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-1"
                  >
                    <option value="state">State</option>
                    <option value="semi_state">Semi-state</option>
                    <option value="independent">Independent</option>
                    <option value="diaspora">Diaspora</option>
                  </select>

                  <select
                    value={draft.factional_alignment}
                    onChange={(e) =>
                      setDrafts((p) => ({
                        ...p,
                        [s.slug]: { ...draft, factional_alignment: e.target.value as Faction },
                      }))
                    }
                    className="text-[12px] border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-1"
                  >
                    <option value="">—</option>
                    <option value="hardline">Hardline</option>
                    <option value="principlist">Principlist</option>
                    <option value="reformist">Reformist</option>
                    <option value="opposition">Opposition</option>
                    <option value="monarchist">Monarchist</option>
                    <option value="radical">Radical</option>
                  </select>

                  <label className="flex items-center gap-1 text-[12px] text-slate-600 dark:text-slate-400">
                    <input
                      type="checkbox"
                      checked={draft.irgc_affiliated}
                      onChange={(e) =>
                        setDrafts((p) => ({
                          ...p,
                          [s.slug]: { ...draft, irgc_affiliated: e.target.checked },
                        }))
                      }
                    />
                    IRGC
                  </label>

                  <label className="flex items-center gap-1 text-[12px] text-slate-600 dark:text-slate-400">
                    <input
                      type="checkbox"
                      checked={draft.is_active}
                      onChange={(e) =>
                        setDrafts((p) => ({
                          ...p,
                          [s.slug]: { ...draft, is_active: e.target.checked },
                        }))
                      }
                    />
                    Active
                  </label>

                  <button
                    type="button"
                    onClick={() => save(s.slug)}
                    disabled={!dirty || saving === s.slug}
                    className="text-[12px] font-bold px-3 py-1 bg-slate-900 dark:bg-white text-white dark:text-slate-900 disabled:opacity-40"
                  >
                    {saving === s.slug ? "…" : "Save"}
                  </button>

                  {saveStatus === "saved" && (
                    <span className="text-[12px] text-emerald-500">✓</span>
                  )}
                  {saveStatus === "error" && (
                    <span className="text-[12px] text-rose-500">Error</span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
