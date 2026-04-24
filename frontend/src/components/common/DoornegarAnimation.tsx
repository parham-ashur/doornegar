"use client";

import { useEffect, useRef } from "react";

type Size = "footer";

// ─── Day-based seeded random ───────────────────────────
function seedFromDate(): number {
  const d = new Date().toDateString();
  let h = 0;
  for (let i = 0; i < d.length; i++) h = ((h << 5) - h + d.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function seededRandom(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 16807 + 0) % 2147483647;
    return s / 2147483647;
  };
}

// ─── Four-subgroup palette ──────────────────────────────────
// Echoes the 4-subgroup taxonomy shown on story pages:
//   principlist       — dark navy   (#1e3a5f light / #93c5fd dark)
//   reformist         — slate blue  (#4f7cac light / #7ba3cf dark)
//   moderate_diaspora — warm amber  (#f97316 light / #fdba74 dark)
//   radical_diaspora  — deep orange (#c2410c light / #fb923c dark)
// Each constellation's stars are split across all four subgroups so
// the whole shape only emerges when you read every color together.
const COLOR_PRINCIPLIST_LIGHT = "#1e3a5f";
const COLOR_PRINCIPLIST_DARK  = "#93c5fd";
const COLOR_REFORMIST_LIGHT   = "#4f7cac";
const COLOR_REFORMIST_DARK    = "#7ba3cf";
const COLOR_MOD_LIGHT         = "#f97316";
const COLOR_MOD_DARK          = "#fdba74";
const COLOR_RAD_LIGHT         = "#c2410c";
const COLOR_RAD_DARK          = "#fb923c";
const COLOR_LINE_LIGHT        = "#94a3b8";
const COLOR_LINE_DARK         = "#64748b";

function getThemeColors(isDark: boolean) {
  return {
    principlist:       isDark ? COLOR_PRINCIPLIST_DARK : COLOR_PRINCIPLIST_LIGHT,
    reformist:         isDark ? COLOR_REFORMIST_DARK   : COLOR_REFORMIST_LIGHT,
    moderate_diaspora: isDark ? COLOR_MOD_DARK         : COLOR_MOD_LIGHT,
    radical_diaspora:  isDark ? COLOR_RAD_DARK         : COLOR_RAD_LIGHT,
    line:              isDark ? COLOR_LINE_DARK        : COLOR_LINE_LIGHT,
  };
}

// Star group: 0=principlist, 1=reformist, 2=moderate_diaspora, 3=radical_diaspora.
// Kept numeric so existing constellation data can use side:0|1 and we
// auto-derive: side 0 → group {0 or 1 alternating by index}, side 1 →
// group {2 or 3 alternating}. A constellation can override by setting
// `group` explicitly on a star.
type Group = 0 | 1 | 2 | 3;
const GROUP_KEYS: Array<keyof ReturnType<typeof getThemeColors>> = [
  "principlist",
  "reformist",
  "moderate_diaspora",
  "radical_diaspora",
];

// ─── Constellations ────────────────────────────────────
// Each shape is designed to read at 110×110 with 5–8 stars. Coordinates
// are normalized 0-1 and scaled into an 82% centered box. `side: 1`
// means the star is drawn in the outside (orange) color; omitted
// means inside (navy).
interface Star { x: number; y: number; bright?: boolean; side?: 0 | 1; group?: Group; }
interface Constellation {
  name_fa: string;
  icon: string;
  stars: Star[];
  lines: [number, number][];
}

const CONSTELLATIONS: Constellation[] = [
  // 1. Orion — left half inside, right half outside
  {
    name_fa: "جبار",
    icon: "🌟",
    stars: [
      { x: 0.50, y: 0.10 },                                  // head (in)
      { x: 0.28, y: 0.25, bright: true },                    // L shoulder (in)
      { x: 0.70, y: 0.27, side: 1 },                         // R shoulder (out)
      { x: 0.40, y: 0.52 },                                  // belt L (in)
      { x: 0.50, y: 0.52 },                                  // belt M (in)
      { x: 0.60, y: 0.52, side: 1 },                         // belt R (out)
      { x: 0.30, y: 0.85, bright: true },                    // L foot (in)
      { x: 0.72, y: 0.83, side: 1 },                         // R foot (out)
    ],
    lines: [
      [0, 1], [0, 2],
      [1, 3], [2, 5],
      [3, 4], [4, 5],
      [3, 6], [5, 7],
    ],
  },
  // 2. Big Dipper — bowl inside, handle outside
  {
    name_fa: "دب اکبر",
    icon: "🥄",
    stars: [
      { x: 0.18, y: 0.45 },
      { x: 0.40, y: 0.32, bright: true },
      { x: 0.42, y: 0.55 },
      { x: 0.20, y: 0.65 },
      { x: 0.58, y: 0.42, side: 1 },
      { x: 0.75, y: 0.30, side: 1 },
      { x: 0.92, y: 0.22, side: 1 },
    ],
    lines: [
      [0, 1], [1, 2], [2, 3], [3, 0],
      [2, 4], [4, 5], [5, 6],
    ],
  },
  // 3. Cassiopeia — alternating W
  {
    name_fa: "ذات‌الکرسی",
    icon: "👑",
    stars: [
      { x: 0.10, y: 0.50 },
      { x: 0.30, y: 0.72, side: 1 },
      { x: 0.50, y: 0.45, bright: true },
      { x: 0.68, y: 0.72, side: 1 },
      { x: 0.90, y: 0.52 },
    ],
    lines: [[0, 1], [1, 2], [2, 3], [3, 4]],
  },
  // 4. Cygnus — vertical arm inside, wings outside
  {
    name_fa: "قوس",
    icon: "🦢",
    stars: [
      { x: 0.50, y: 0.10, bright: true },
      { x: 0.50, y: 0.50 },
      { x: 0.50, y: 0.90 },
      { x: 0.12, y: 0.48, side: 1 },
      { x: 0.88, y: 0.52, side: 1 },
    ],
    lines: [[0, 1], [1, 2], [3, 1], [1, 4]],
  },
  // 5. Lyra — Vega + upper strings inside, lower inside/outside mix
  {
    name_fa: "چنگ",
    icon: "🎼",
    stars: [
      { x: 0.50, y: 0.12, bright: true },
      { x: 0.32, y: 0.42 },
      { x: 0.68, y: 0.40, side: 1 },
      { x: 0.28, y: 0.78 },
      { x: 0.72, y: 0.80, side: 1 },
    ],
    lines: [[0, 1], [0, 2], [1, 2], [1, 3], [2, 4], [3, 4]],
  },
  // 6. Scorpius — head/body inside, tail/stinger outside
  {
    name_fa: "عقرب",
    icon: "🦂",
    stars: [
      { x: 0.15, y: 0.35 },
      { x: 0.22, y: 0.48 },
      { x: 0.35, y: 0.55, bright: true },
      { x: 0.48, y: 0.62 },
      { x: 0.60, y: 0.68, side: 1 },
      { x: 0.72, y: 0.68, side: 1 },
      { x: 0.82, y: 0.55, side: 1 },
      { x: 0.76, y: 0.40, side: 1 },
    ],
    lines: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7]],
  },
  // 7. Pleiades — alternating cluster
  {
    name_fa: "ثریا",
    icon: "✨",
    stars: [
      { x: 0.35, y: 0.35, bright: true },
      { x: 0.55, y: 0.30, side: 1 },
      { x: 0.50, y: 0.48 },
      { x: 0.68, y: 0.42, side: 1 },
      { x: 0.40, y: 0.58 },
      { x: 0.62, y: 0.62, side: 1 },
      { x: 0.48, y: 0.72, bright: true },
    ],
    lines: [[0, 1], [1, 3], [3, 5], [5, 6], [6, 4], [4, 0]],
  },
  // 8. Sailboat — sail inside, hull outside
  {
    name_fa: "قایق",
    icon: "⛵",
    stars: [
      { x: 0.55, y: 0.10 },
      { x: 0.20, y: 0.62 },
      { x: 0.55, y: 0.65 },
      { x: 0.15, y: 0.78, side: 1 },
      { x: 0.50, y: 0.92, side: 1 },
      { x: 0.88, y: 0.78, side: 1 },
    ],
    lines: [
      [0, 2],
      [0, 1], [1, 2],
      [3, 4], [4, 5],
      [3, 2], [5, 2],
    ],
  },
  // 9. Crown — left half outside, right half inside, center bridges
  {
    name_fa: "تاج",
    icon: "👑",
    stars: [
      { x: 0.12, y: 0.68, side: 1 },
      { x: 0.26, y: 0.38, side: 1 },
      { x: 0.40, y: 0.55, side: 1 },
      { x: 0.50, y: 0.22, bright: true },
      { x: 0.60, y: 0.55 },
      { x: 0.74, y: 0.38 },
      { x: 0.88, y: 0.68 },
    ],
    lines: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [0, 6]],
  },
  // 10. Kite — kite inside, tail outside
  {
    name_fa: "بادبادک",
    icon: "🪁",
    stars: [
      { x: 0.50, y: 0.10 },
      { x: 0.78, y: 0.32 },
      { x: 0.50, y: 0.55 },
      { x: 0.22, y: 0.32 },
      { x: 0.56, y: 0.70, side: 1 },
      { x: 0.44, y: 0.82, side: 1 },
      { x: 0.55, y: 0.92, side: 1 },
    ],
    lines: [[0, 1], [1, 2], [2, 3], [3, 0], [2, 4], [4, 5], [5, 6]],
  },
  // 11. Hourglass — top inside, bottom outside, center bridges
  {
    name_fa: "ساعت شنی",
    icon: "⏳",
    stars: [
      { x: 0.22, y: 0.12 },
      { x: 0.78, y: 0.12 },
      { x: 0.50, y: 0.50, bright: true },
      { x: 0.22, y: 0.88, side: 1 },
      { x: 0.78, y: 0.88, side: 1 },
    ],
    lines: [[0, 1], [0, 2], [1, 2], [2, 3], [2, 4], [3, 4]],
  },
  // 12. Cypress — zigzag sides alternating
  {
    name_fa: "سرو",
    icon: "🌲",
    stars: [
      { x: 0.50, y: 0.08, bright: true },
      { x: 0.36, y: 0.28 },
      { x: 0.64, y: 0.28, side: 1 },
      { x: 0.30, y: 0.50 },
      { x: 0.70, y: 0.50, side: 1 },
      { x: 0.36, y: 0.72 },
      { x: 0.64, y: 0.72, side: 1 },
      { x: 0.50, y: 0.92 },
    ],
    lines: [
      [0, 1], [0, 2],
      [1, 3], [2, 4],
      [3, 5], [4, 6],
      [5, 7], [6, 7],
    ],
  },
  // 13. Butterfly — body inside, right wing outside, left wing inside
  {
    name_fa: "پروانه",
    icon: "🦋",
    stars: [
      { x: 0.50, y: 0.22 },
      { x: 0.50, y: 0.50 },
      { x: 0.50, y: 0.78 },
      { x: 0.12, y: 0.22 },
      { x: 0.88, y: 0.22, side: 1 },
      { x: 0.18, y: 0.82 },
      { x: 0.82, y: 0.82, side: 1 },
    ],
    lines: [
      [0, 1], [1, 2],
      [0, 3], [3, 1],
      [0, 4], [4, 1],
      [1, 5], [5, 2],
      [1, 6], [6, 2],
    ],
  },
  // 14. Tulip — left petal inside, right petal outside, stem inside
  {
    name_fa: "لاله",
    icon: "🌷",
    stars: [
      { x: 0.32, y: 0.28 },
      { x: 0.50, y: 0.15, bright: true },
      { x: 0.68, y: 0.28, side: 1 },
      { x: 0.35, y: 0.52 },
      { x: 0.65, y: 0.52, side: 1 },
      { x: 0.50, y: 0.92 },
    ],
    lines: [
      [0, 1], [1, 2],
      [0, 3], [2, 4],
      [3, 4],
      [3, 5], [4, 5],
    ],
  },
  // 15. Bow — bow inside, arrow outside
  {
    name_fa: "کمان",
    icon: "🏹",
    stars: [
      { x: 0.22, y: 0.12 },
      { x: 0.36, y: 0.32 },
      { x: 0.42, y: 0.50, bright: true },
      { x: 0.36, y: 0.68 },
      { x: 0.22, y: 0.88 },
      { x: 0.88, y: 0.50, side: 1 },
    ],
    lines: [
      [0, 1], [1, 2], [2, 3], [3, 4],
      [0, 4],
      [2, 5],
    ],
  },
  // 16. Compass rose — cardinals inside, diagonals outside
  {
    name_fa: "قطب‌نما",
    icon: "🧭",
    stars: [
      { x: 0.50, y: 0.05 },
      { x: 0.66, y: 0.34, side: 1 },
      { x: 0.95, y: 0.50 },
      { x: 0.66, y: 0.66, side: 1 },
      { x: 0.50, y: 0.95 },
      { x: 0.34, y: 0.66, side: 1 },
      { x: 0.05, y: 0.50 },
      { x: 0.34, y: 0.34, side: 1 },
      { x: 0.50, y: 0.50, bright: true },
    ],
    lines: [
      [0, 1], [1, 2], [2, 3], [3, 4],
      [4, 5], [5, 6], [6, 7], [7, 0],
    ],
  },
];

// ─── Helpers ───────────────────────────────────────────

function hexWithAlpha(hex: string, alpha: number): string {
  const a = Math.max(0, Math.min(1, alpha));
  const hex8 = Math.round(a * 255).toString(16).padStart(2, "0");
  return hex + hex8;
}

// Chaos → midpoint → target, smoothstep on each half. Same feel as the
// previous animation but applied per-star instead of per-segment.
function sCurve(a: number, mid: number, b: number, t: number): number {
  if (t < 0.5) {
    const p = t / 0.5;
    const ease = p * p * (3 - 2 * p);
    return a + (mid - a) * ease;
  } else {
    const p = (t - 0.5) / 0.5;
    const ease = p * p * (3 - 2 * p);
    return mid + (b - mid) * ease;
  }
}

interface StarDisplay {
  // 4-subgroup color index, fixed for the star's lifetime so identity
  // persists through pose morphs.
  group: Group;
  // Whether this is a "bright" anchor star (slightly larger). Fixed per
  // star so size doesn't flicker across poses.
  bright: boolean;
  // Tiny always-on wander so settled stars still breathe. One orbit
  // per axis with small amplitude.
  wanderAx: number; wanderAy: number;
  wanderFx: number; wanderFy: number;
  wanderPx: number; wanderPy: number;
  // Target positions, one per pose. Same length as `poseOrder`.
  posePositions: Array<{ x: number; y: number }>;
}

interface FieldStar {
  x: number; y: number; r: number; alpha: number; twinkleOffset: number;
}

// Fixed display-star count. Each pose maps its constellation's stars
// onto these 8 slots (cycling if the constellation has fewer), so the
// same 8 glowing dots morph between constellations instead of spawning
// /despawning per pose.
const DISPLAY_STARS = 8;

// ─── Component ─────────────────────────────────────────

export default function DoornegarAnimation({ size = "footer" }: { size?: Size }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const seedRef = useRef(seedFromDate());
  const triggeredRef = useRef(false);

  const starsRef = useRef<StarDisplay[]>([]);
  const fieldStarsRef = useRef<FieldStar[]>([]);
  const poseOrderRef = useRef<number[]>([]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const seed = seedRef.current;

    // Deterministic pose sequence for the day: every constellation
    // shuffled by the same seed so the whole footer tells one coherent
    // story across a full visit.
    const rngOrder = seededRandom(seed ^ 0x5a5a5a5a);
    const poseOrder = CONSTELLATIONS.map((_, i) => i);
    for (let i = poseOrder.length - 1; i > 0; i--) {
      const j = Math.floor(rngOrder() * (i + 1));
      [poseOrder[i], poseOrder[j]] = [poseOrder[j], poseOrder[i]];
    }
    poseOrderRef.current = poseOrder;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      const ctx = canvas.getContext("2d");
      if (ctx) ctx.scale(dpr, dpr);

      const w = rect.width;
      const h = rect.height;
      const boxSize = Math.min(w, h) * 0.82;
      const bx = (w - boxSize) / 2;
      const by = (h - boxSize) / 2;

      const rng = seededRandom(seed);

      // Precompute each display star's 4-subgroup color + tiny wander
      // motion + the target position it takes in every pose. Cycling
      // through constellation.stars when the constellation has fewer
      // than DISPLAY_STARS keeps the mapping stable without introducing
      // fades in/out.
      const stars: StarDisplay[] = [];
      for (let i = 0; i < DISPLAY_STARS; i++) {
        // Two principlist + two reformist on the "right" half, two
        // moderate + two radical on the "left" half — balanced 4-color
        // spread that stays consistent across all poses.
        const group: Group = (i % 4) as Group;
        const bright = i === 0 || i === 4;
        const posePositions = poseOrder.map((poseIdx) => {
          const c = CONSTELLATIONS[poseIdx];
          const starDef = c.stars[i % c.stars.length];
          return {
            x: bx + starDef.x * boxSize,
            y: by + starDef.y * boxSize,
          };
        });
        stars.push({
          group,
          bright,
          wanderAx: w * (0.015 + rng() * 0.02),
          wanderAy: h * (0.015 + rng() * 0.02),
          wanderFx: 0.35 + rng() * 0.4,
          wanderFy: 0.3 + rng() * 0.4,
          wanderPx: rng() * Math.PI * 2,
          wanderPy: rng() * Math.PI * 2,
          posePositions,
        });
      }
      starsRef.current = stars;

      // Background field stars — static decorative dust to suggest depth
      const fieldCount = 9;
      fieldStarsRef.current = Array.from({ length: fieldCount }, () => ({
        x: rng() * w,
        y: rng() * h,
        r: 0.3 + rng() * 0.8,
        alpha: 0.10 + rng() * 0.18,
        twinkleOffset: rng() * Math.PI * 2,
      }));
    };

    let cachedW = 0, cachedH = 0;
    const updateCachedSize = () => {
      const r = canvas.getBoundingClientRect();
      cachedW = r.width;
      cachedH = r.height;
    };
    updateCachedSize();

    const smoothstep = (x: number) => {
      const t = Math.max(0, Math.min(1, x));
      return t * t * (3 - 2 * t);
    };

    // ── Pose cycle: slow morph between constellations ───────────────
    //
    // Each pose lasts POSE_MS. Within a pose window we run a smoothstep
    // from the previous constellation's positions to the current one,
    // so stars always ease *in* to the shape and ease *out* before the
    // next. No hold-in-place interval — the smoothstep flatness at
    // both endpoints already reads as "settled" at arrival and
    // "departing" just before the next morph. Result is the slow
    // breathing feel Parham asked for, rather than a snap-and-release.
    const POSE_MS = 7000;

    const draw = (timestamp: number) => {
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const time = timestamp * 0.001;
      const poseIdx = Math.floor(timestamp / POSE_MS) % poseOrderRef.current.length;
      const prevIdx = (poseIdx - 1 + poseOrderRef.current.length) % poseOrderRef.current.length;
      const rawT = (timestamp % POSE_MS) / POSE_MS;
      const morphT = smoothstep(rawT);

      const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      ctx.fillStyle = isDark ? "#0a0e1a" : "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // ── Background field stars ──
      const fieldColor = isDark ? "#ffffff" : "#334155";
      for (const fs of fieldStarsRef.current) {
        const twinkle = 0.75 + 0.25 * Math.sin(time * 1.4 + fs.twinkleOffset);
        ctx.fillStyle = hexWithAlpha(fieldColor, fs.alpha * twinkle);
        ctx.beginPath();
        ctx.arc(fs.x, fs.y, fs.r, 0, Math.PI * 2);
        ctx.fill();
      }

      const stars = starsRef.current;
      const themeColors = getThemeColors(isDark);

      for (let i = 0; i < stars.length; i++) {
        const st = stars[i];
        const prev = st.posePositions[prevIdx];
        const cur = st.posePositions[poseIdx];

        // Morph smoothly between the two anchors, add always-on micro-wander.
        const anchorX = prev.x + (cur.x - prev.x) * morphT;
        const anchorY = prev.y + (cur.y - prev.y) * morphT;
        const px = anchorX + Math.sin(time * st.wanderFx + st.wanderPx) * st.wanderAx;
        const py = anchorY + Math.cos(time * st.wanderFy + st.wanderPy) * st.wanderAy;

        const baseR = st.bright ? 2.4 : 1.7;
        const glowR = st.bright ? 6 : 4;
        const starColor = themeColors[GROUP_KEYS[st.group]];

        // Brightness eases up when settled into a pose (near pose center,
        // rawT ≈ 0.5), and dims slightly during the morph travel. Plus a
        // gentle sinusoidal twinkle so no star ever looks frozen.
        const settledness = 1 - Math.abs(rawT - 0.5) * 2; // 0 at edges, 1 at center
        const twinkle = 0.82 + 0.18 * Math.sin(time * 1.6 + i * 1.37);
        const alpha = twinkle * (0.75 + 0.25 * smoothstep(settledness));

        // Glow halo
        const glow = ctx.createRadialGradient(px, py, 0, px, py, glowR);
        glow.addColorStop(0, hexWithAlpha(starColor, 0.42 * alpha));
        glow.addColorStop(1, hexWithAlpha(starColor, 0));
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(px, py, glowR, 0, Math.PI * 2);
        ctx.fill();

        // Core
        ctx.fillStyle = hexWithAlpha(starColor, alpha);
        ctx.beginPath();
        ctx.arc(px, py, baseR, 0, Math.PI * 2);
        ctx.fill();
      }

      animRef.current = requestAnimationFrame(draw);
    };

    resize();
    updateCachedSize();

    const handleResize = () => { resize(); updateCachedSize(); };

    // Scroll-triggered: start when the canvas enters the viewport
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !triggeredRef.current) {
          triggeredRef.current = true;
          animRef.current = requestAnimationFrame(draw);
        }
      },
      { threshold: 0.3 }
    );
    observer.observe(canvas);

    window.addEventListener("resize", handleResize);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animRef.current);
    };
  }, [size]);

  const sizeClasses: Record<Size, string> = {
    footer: "w-[110px] h-[110px]",
  };

  return (
    <canvas
      ref={canvasRef}
      className={sizeClasses[size]}
      style={{ display: "block" }}
      role="img"
      aria-label="دورنگر"
    />
  );
}
