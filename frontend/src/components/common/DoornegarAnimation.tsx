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

// ─── Muted color palettes (rotated daily) ──────────────
const PALETTES = [
  ["#b07d62", "#7a9e8e", "#8a9ab5"],
  ["#c4886d", "#6b8f71", "#7986a8"],
  ["#a0855e", "#5e9b8a", "#9a7fb0"],
  ["#c97b7b", "#7bab8a", "#7b9cc9"],
  ["#8b7355", "#5a8a7a", "#8b7aaa"],
  ["#a38d6d", "#6da08e", "#6d8aaa"],
  ["#b5856b", "#6b9980", "#856bb5"],
];

// ─── Figures ───────────────────────────────────────────
// "triangle" points apex-up (base on bottom), "triangleDown" points apex-down
// (base on top). The two together are what you need for hexagrams and
// hourglasses — pairing two apex-up triangles just stacks them.
type ShapeType = "triangle" | "triangleDown" | "square" | "circle" | "diamond" | "line";
interface ShapeDef {
  type: ShapeType;
  cx: number; cy: number;
  s: number;
  colorIdx: number;
}

const FIGURE_ICONS = [
  "🏠", "🌳", "🧑", "⛵", "🐦", "⛰️",
  "⭐", "🌸", "🐱", "👑", "🏮", "🐟",
  "⏳", "🔑", "👁️", "🦋", "☂️", "🌙",
];

const FIGURE_NAMES_FA = [
  "خانه", "درخت", "انسان", "قایق", "پرنده", "کوه",
  "ستاره", "گل", "گربه", "تاج", "فانوس", "ماهی",
  "ساعت شنی", "کلید", "چشم", "پروانه", "چتر", "ماه",
];

export function getTodayIcon(): string {
  return FIGURE_ICONS[seedFromDate() % FIGURE_ICONS.length];
}

export function getTodayName(): string {
  return FIGURE_NAMES_FA[seedFromDate() % FIGURE_NAMES_FA.length];
}

const FIGURES: ShapeDef[][] = [
  // House
  [
    { type: "triangle", cx: 0.5, cy: 0.25, s: 0.5, colorIdx: 0 },
    { type: "square", cx: 0.5, cy: 0.6, s: 0.4, colorIdx: 1 },
    { type: "square", cx: 0.5, cy: 0.75, s: 0.12, colorIdx: 2 },
  ],
  // Tree
  [
    { type: "triangle", cx: 0.5, cy: 0.2, s: 0.5, colorIdx: 1 },
    { type: "triangle", cx: 0.5, cy: 0.4, s: 0.4, colorIdx: 1 },
    { type: "square", cx: 0.5, cy: 0.7, s: 0.1, colorIdx: 0 },
    { type: "circle", cx: 0.5, cy: 0.12, s: 0.08, colorIdx: 2 },
  ],
  // Person
  [
    { type: "circle", cx: 0.5, cy: 0.2, s: 0.15, colorIdx: 0 },
    { type: "triangle", cx: 0.5, cy: 0.5, s: 0.35, colorIdx: 1 },
    { type: "line", cx: 0.38, cy: 0.78, s: 0.2, colorIdx: 2 },
    { type: "line", cx: 0.62, cy: 0.78, s: 0.2, colorIdx: 2 },
  ],
  // Boat
  [
    { type: "triangle", cx: 0.55, cy: 0.3, s: 0.35, colorIdx: 2 },
    { type: "diamond", cx: 0.5, cy: 0.65, s: 0.5, colorIdx: 0 },
    { type: "line", cx: 0.5, cy: 0.55, s: 0.4, colorIdx: 1 },
  ],
  // Bird
  [
    { type: "circle", cx: 0.65, cy: 0.35, s: 0.08, colorIdx: 0 },
    { type: "triangle", cx: 0.4, cy: 0.35, s: 0.3, colorIdx: 1 },
    { type: "triangle", cx: 0.35, cy: 0.5, s: 0.25, colorIdx: 2 },
  ],
  // Mountain
  [
    { type: "triangle", cx: 0.5, cy: 0.35, s: 0.6, colorIdx: 1 },
    { type: "triangle", cx: 0.75, cy: 0.5, s: 0.35, colorIdx: 2 },
    { type: "circle", cx: 0.25, cy: 0.25, s: 0.1, colorIdx: 0 },
  ],
  // Star — two equal triangles sharing a center form a hexagram (Star of
  // David / ستاره داود). Before, both pointed up so the result was two
  // stacked triangles, not a star.
  [
    { type: "triangle", cx: 0.5, cy: 0.5, s: 0.3, colorIdx: 0 },
    { type: "triangleDown", cx: 0.5, cy: 0.5, s: 0.3, colorIdx: 0 },
    { type: "circle", cx: 0.5, cy: 0.5, s: 0.07, colorIdx: 2 },
  ],
  // Flower
  [
    { type: "circle", cx: 0.5, cy: 0.4, s: 0.12, colorIdx: 0 },
    { type: "diamond", cx: 0.5, cy: 0.22, s: 0.15, colorIdx: 1 },
    { type: "diamond", cx: 0.35, cy: 0.4, s: 0.15, colorIdx: 1 },
    { type: "diamond", cx: 0.65, cy: 0.4, s: 0.15, colorIdx: 2 },
    { type: "diamond", cx: 0.5, cy: 0.58, s: 0.15, colorIdx: 2 },
    { type: "line", cx: 0.5, cy: 0.78, s: 0.2, colorIdx: 1 },
  ],
  // Cat
  [
    { type: "circle", cx: 0.5, cy: 0.35, s: 0.2, colorIdx: 0 },
    { type: "triangle", cx: 0.38, cy: 0.2, s: 0.1, colorIdx: 0 },
    { type: "triangle", cx: 0.62, cy: 0.2, s: 0.1, colorIdx: 0 },
    { type: "square", cx: 0.5, cy: 0.6, s: 0.22, colorIdx: 1 },
    { type: "line", cx: 0.7, cy: 0.65, s: 0.18, colorIdx: 2 },
  ],
  // Crown
  [
    { type: "square", cx: 0.5, cy: 0.6, s: 0.35, colorIdx: 1 },
    { type: "triangle", cx: 0.3, cy: 0.35, s: 0.18, colorIdx: 0 },
    { type: "triangle", cx: 0.5, cy: 0.3, s: 0.2, colorIdx: 0 },
    { type: "triangle", cx: 0.7, cy: 0.35, s: 0.18, colorIdx: 0 },
    { type: "circle", cx: 0.5, cy: 0.45, s: 0.06, colorIdx: 2 },
  ],
  // Lantern
  [
    { type: "triangle", cx: 0.5, cy: 0.2, s: 0.15, colorIdx: 2 },
    { type: "diamond", cx: 0.5, cy: 0.45, s: 0.25, colorIdx: 0 },
    { type: "circle", cx: 0.5, cy: 0.45, s: 0.1, colorIdx: 1 },
    { type: "line", cx: 0.5, cy: 0.7, s: 0.12, colorIdx: 2 },
  ],
  // Fish
  [
    { type: "diamond", cx: 0.45, cy: 0.5, s: 0.3, colorIdx: 1 },
    { type: "triangle", cx: 0.75, cy: 0.5, s: 0.2, colorIdx: 2 },
    { type: "circle", cx: 0.35, cy: 0.45, s: 0.05, colorIdx: 0 },
  ],
  // Hourglass (ساعت شنی): top triangle apex-down, bottom apex-up, meeting
  // at the pinch point in the middle so the shape reads as a real hourglass.
  [
    { type: "triangleDown", cx: 0.5, cy: 0.3, s: 0.22, colorIdx: 0 },
    { type: "triangle", cx: 0.5, cy: 0.7, s: 0.22, colorIdx: 2 },
    { type: "circle", cx: 0.5, cy: 0.5, s: 0.04, colorIdx: 1 },
  ],
  // Key
  [
    { type: "circle", cx: 0.35, cy: 0.4, s: 0.18, colorIdx: 0 },
    { type: "square", cx: 0.55, cy: 0.4, s: 0.06, colorIdx: 1 },
    { type: "square", cx: 0.7, cy: 0.5, s: 0.06, colorIdx: 2 },
    { type: "square", cx: 0.78, cy: 0.5, s: 0.06, colorIdx: 2 },
  ],
  // Eye
  [
    { type: "diamond", cx: 0.5, cy: 0.5, s: 0.35, colorIdx: 1 },
    { type: "circle", cx: 0.5, cy: 0.5, s: 0.15, colorIdx: 0 },
    { type: "circle", cx: 0.5, cy: 0.5, s: 0.06, colorIdx: 2 },
  ],
  // Butterfly
  [
    { type: "diamond", cx: 0.3, cy: 0.4, s: 0.22, colorIdx: 1 },
    { type: "diamond", cx: 0.7, cy: 0.4, s: 0.22, colorIdx: 2 },
    { type: "diamond", cx: 0.3, cy: 0.6, s: 0.18, colorIdx: 2 },
    { type: "diamond", cx: 0.7, cy: 0.6, s: 0.18, colorIdx: 1 },
    { type: "line", cx: 0.5, cy: 0.5, s: 0.3, colorIdx: 0 },
  ],
  // Umbrella
  [
    { type: "circle", cx: 0.5, cy: 0.35, s: 0.3, colorIdx: 0 },
    { type: "line", cx: 0.5, cy: 0.6, s: 0.25, colorIdx: 1 },
    { type: "diamond", cx: 0.5, cy: 0.8, s: 0.08, colorIdx: 2 },
  ],
  // Moon and stars
  [
    { type: "circle", cx: 0.4, cy: 0.45, s: 0.25, colorIdx: 0 },
    { type: "triangle", cx: 0.7, cy: 0.3, s: 0.08, colorIdx: 1 },
    { type: "triangle", cx: 0.75, cy: 0.55, s: 0.06, colorIdx: 2 },
    { type: "triangle", cx: 0.6, cy: 0.65, s: 0.07, colorIdx: 1 },
  ],
];

// ─── Convert shape to line segments ────────────────────
interface Segment {
  x1: number; y1: number; x2: number; y2: number;
  color: string;
  cx1: number; cy1: number; cx2: number; cy2: number;
  // S-curve drift control points
  drift1x: number; drift1y: number;
  drift2x: number; drift2y: number;
}

function shapeToSegments(
  shape: ShapeDef, bx: number, by: number, bw: number, bh: number,
  color: string, rng: () => number, fullW: number, fullH: number,
): Segment[] {
  const cx = bx + shape.cx * bw;
  const cy = by + shape.cy * bh;
  const s = shape.s * Math.min(bw, bh) * 0.5;
  const segs: Segment[] = [];

  const addSeg = (x1: number, y1: number, x2: number, y2: number) => {
    // Chaos start: scattered far, as if drifting in space
    const angle1 = rng() * Math.PI * 2;
    const dist1 = fullW * 0.4 + rng() * fullW * 0.6;
    const angle2 = rng() * Math.PI * 2;
    const dist2 = fullW * 0.4 + rng() * fullW * 0.6;
    // S-curve midpoints: offset from the straight path
    const mid1x = (x1 + rng() * fullW) * 0.5 + (rng() - 0.5) * fullW * 0.4;
    const mid1y = (y1 + rng() * fullH) * 0.5 + (rng() - 0.5) * fullH * 0.4;
    const mid2x = (x2 + rng() * fullW) * 0.5 + (rng() - 0.5) * fullW * 0.4;
    const mid2y = (y2 + rng() * fullH) * 0.5 + (rng() - 0.5) * fullH * 0.4;

    segs.push({
      x1, y1, x2, y2, color,
      cx1: fullW * 0.5 + Math.cos(angle1) * dist1,
      cy1: fullH * 0.5 + Math.sin(angle1) * dist1,
      cx2: fullW * 0.5 + Math.cos(angle2) * dist2,
      cy2: fullH * 0.5 + Math.sin(angle2) * dist2,
      drift1x: mid1x, drift1y: mid1y,
      drift2x: mid2x, drift2y: mid2y,
    });
  };

  switch (shape.type) {
    case "triangle":
      addSeg(cx, cy - s, cx - s, cy + s);
      addSeg(cx - s, cy + s, cx + s, cy + s);
      addSeg(cx + s, cy + s, cx, cy - s);
      break;
    case "triangleDown":
      addSeg(cx, cy + s, cx - s, cy - s);
      addSeg(cx - s, cy - s, cx + s, cy - s);
      addSeg(cx + s, cy - s, cx, cy + s);
      break;
    case "square":
      addSeg(cx - s, cy - s, cx + s, cy - s);
      addSeg(cx + s, cy - s, cx + s, cy + s);
      addSeg(cx + s, cy + s, cx - s, cy + s);
      addSeg(cx - s, cy + s, cx - s, cy - s);
      break;
    case "circle": {
      const n = 8;
      for (let i = 0; i < n; i++) {
        const a1 = (i / n) * Math.PI * 2;
        const a2 = ((i + 1) / n) * Math.PI * 2;
        addSeg(cx + Math.cos(a1) * s, cy + Math.sin(a1) * s, cx + Math.cos(a2) * s, cy + Math.sin(a2) * s);
      }
      break;
    }
    case "diamond":
      addSeg(cx, cy - s, cx + s, cy);
      addSeg(cx + s, cy, cx, cy + s * 0.5);
      addSeg(cx, cy + s * 0.5, cx - s, cy);
      addSeg(cx - s, cy, cx, cy - s);
      break;
    case "line":
      addSeg(cx, cy - s, cx, cy + s);
      break;
  }
  return segs;
}

// Smooth S-curve: chaos → drift through space → settle
// Uses cubic hermite for a natural, organic path with no sudden changes
function sCurve(chaos: number, drift: number, target: number, t: number): number {
  // Smooth step function for overall easing
  const smooth = t * t * (3 - 2 * t); // smoothstep 0→1

  if (t < 0.5) {
    // First half: chaos → drift with gentle acceleration
    const p = t / 0.5;
    const ease = p * p * (3 - 2 * p); // smoothstep
    return chaos + (drift - chaos) * ease;
  } else {
    // Second half: drift → target with gentle deceleration
    const p = (t - 0.5) / 0.5;
    const ease = p * p * (3 - 2 * p); // smoothstep
    return drift + (target - drift) * ease;
  }
}

// ─── Component ─────────────────────────────────────────

export default function DoornegarAnimation({ size = "footer" }: { size?: Size }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const startRef = useRef<number>(0);
  const formedAtRef = useRef<number>(0); // timestamp when figure completed
  const segmentsRef = useRef<Segment[]>([]);
  const seedRef = useRef(seedFromDate());
  const triggeredRef = useRef(false);

  const duration = 14000; // 14 seconds to form — slow and meditative

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const seed = seedRef.current;
    const palette = PALETTES[seed % PALETTES.length];
    const figure = FIGURES[seed % FIGURES.length];

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      const ctx = canvas.getContext("2d");
      if (ctx) ctx.scale(dpr, dpr);

      const w = rect.width;
      const h = rect.height;
      const boxSize = Math.min(w, h) * 0.8;
      const bx = (w - boxSize) / 2;
      const by = (h - boxSize) / 2;

      const rng = seededRandom(seed);
      const allSegs: Segment[] = [];
      for (const shape of figure) {
        const color = palette[shape.colorIdx % palette.length];
        allSegs.push(...shapeToSegments(shape, bx, by, boxSize, boxSize, color, rng, w, h));
      }
      segmentsRef.current = allSegs;
    };

    // Cache dimensions — only update on resize
    let cachedW = 0, cachedH = 0;
    const updateCachedSize = () => {
      const r = canvas.getBoundingClientRect();
      cachedW = r.width;
      cachedH = r.height;
    };
    updateCachedSize();

    const draw = (timestamp: number) => {
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      if (!startRef.current) startRef.current = timestamp;
      const progress = Math.min((timestamp - startRef.current) / duration, 1);
      const time = timestamp * 0.001;

      const w = cachedW;
      const h = cachedH;

      const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      ctx.fillStyle = isDark ? "#0a0e1a" : "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const centerX = w / 2;
      const centerY = h / 2;
      const radius = Math.min(w, h) / 2 - 1;
      ctx.save();

      const lineWidth = 2;

      // Track when the figure completed forming
      if (progress >= 1 && formedAtRef.current === 0) {
        formedAtRef.current = timestamp;
      }

      // Slow rotation — starts from zero after forming, ramps up gently
      if (formedAtRef.current > 0) {
        const sinceFormed = (timestamp - formedAtRef.current) * 0.001; // seconds since formed
        // Ease into rotation over 3 seconds, then constant
        const rampUp = Math.min(sinceFormed / 3, 1);
        const ease = rampUp * rampUp * (3 - 2 * rampUp); // smoothstep
        const angle = sinceFormed * 0.06 * ease; // 0.06 rad/s ≈ 1 turn per 105s
        ctx.translate(centerX, centerY);
        ctx.rotate(angle);
        ctx.translate(-centerX, -centerY);
      }

      // Line opacity: fade in during first 20% of formation
      const baseOpacity = progress < 0.2 ? progress / 0.2 : 1;

      for (let i = 0; i < segmentsRef.current.length; i++) {
        const seg = segmentsRef.current[i];

        // Each segment has a slightly staggered timing for organic feel
        const stagger = (i / segmentsRef.current.length) * 0.15; // up to 15% delay
        const segProgress = Math.max(0, Math.min((progress - stagger) / (1 - stagger), 1));

        let px1: number, py1: number, px2: number, py2: number;

        if (segProgress < 1) {
          px1 = sCurve(seg.cx1, seg.drift1x, seg.x1, segProgress);
          py1 = sCurve(seg.cy1, seg.drift1y, seg.y1, segProgress);
          px2 = sCurve(seg.cx2, seg.drift2x, seg.x2, segProgress);
          py2 = sCurve(seg.cy2, seg.drift2y, seg.y2, segProgress);
        } else {
          px1 = seg.x1;
          py1 = seg.y1;
          px2 = seg.x2;
          py2 = seg.y2;
        }

        // Segment opacity: fades in with its own timing
        const segOpacity = segProgress < 0.3 ? segProgress / 0.3 : 1;
        const opacity = Math.round(baseOpacity * segOpacity * 255).toString(16).padStart(2, "0");

        ctx.beginPath();
        ctx.moveTo(px1, py1);
        ctx.lineTo(px2, py2);
        ctx.strokeStyle = seg.color + opacity;
        ctx.lineWidth = lineWidth;
        ctx.lineCap = "round";
        ctx.stroke();
      }

      ctx.restore();

      animRef.current = requestAnimationFrame(draw);
    };

    resize();
    updateCachedSize();

    const handleResize = () => { resize(); updateCachedSize(); };

    // Scroll-triggered: start animation when canvas enters viewport
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !triggeredRef.current) {
          triggeredRef.current = true;
          startRef.current = 0;
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
  }, [size, duration]);

  const sizeClasses: Record<Size, string> = {
    footer: "w-[110px] h-[110px]",
  };

  const name = getTodayName();

  return (
    <div className="relative group cursor-default doornegar-tooltip-wrapper">
      <canvas
        ref={canvasRef}
        className={sizeClasses[size]}
        style={{ display: "block" }}
        role="img"
        aria-label="تصویر انتزاعی روزانه دورنگر"
      />
      <span className="doornegar-tooltip absolute -bottom-6 left-1/2 -translate-x-1/2 px-2 py-0.5 text-[10px] font-medium text-slate-500 dark:text-slate-400 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 whitespace-nowrap pointer-events-none">
        {name}
      </span>
      <style>{`
        .doornegar-tooltip {
          opacity: 0;
          transition: opacity 0.3s;
        }
        @media (hover: hover) and (pointer: fine) {
          .doornegar-tooltip-wrapper:hover .doornegar-tooltip {
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
}
