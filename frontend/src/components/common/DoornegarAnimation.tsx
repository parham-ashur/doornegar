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

// ─── Warm starlight palette ────────────────────────────
// Colors chosen to read on both light and dark backgrounds.
const STAR_COLORS = [
  "#b48a4e",
  "#7a8ba0",
  "#a4763e",
  "#8596aa",
  "#b08660",
  "#6b88a5",
  "#ab7c55",
];

// ─── Constellations ────────────────────────────────────
// Each shape is designed to read at 110×110 with 5–8 stars. Coordinates
// are normalized 0-1 and scaled into an 82% centered box.
interface Star { x: number; y: number; bright?: boolean; }
interface Constellation {
  name_fa: string;
  icon: string;
  stars: Star[];
  lines: [number, number][];
}

const CONSTELLATIONS: Constellation[] = [
  // 1. Orion — شکارگر با کمربند سه‌ستاره
  {
    name_fa: "جبار",
    icon: "🌟",
    stars: [
      { x: 0.50, y: 0.10 },
      { x: 0.28, y: 0.25, bright: true },
      { x: 0.70, y: 0.27 },
      { x: 0.40, y: 0.52 },
      { x: 0.50, y: 0.52 },
      { x: 0.60, y: 0.52 },
      { x: 0.30, y: 0.85, bright: true },
      { x: 0.72, y: 0.83 },
    ],
    lines: [
      [0, 1], [0, 2],
      [1, 3], [2, 5],
      [3, 4], [4, 5],
      [3, 6], [5, 7],
    ],
  },
  // 2. Big Dipper
  {
    name_fa: "دب اکبر",
    icon: "🥄",
    stars: [
      { x: 0.18, y: 0.45 },
      { x: 0.40, y: 0.32, bright: true },
      { x: 0.42, y: 0.55 },
      { x: 0.20, y: 0.65 },
      { x: 0.58, y: 0.42 },
      { x: 0.75, y: 0.30 },
      { x: 0.92, y: 0.22 },
    ],
    lines: [
      [0, 1], [1, 2], [2, 3], [3, 0],
      [2, 4], [4, 5], [5, 6],
    ],
  },
  // 3. Cassiopeia — the W
  {
    name_fa: "ذات‌الکرسی",
    icon: "👑",
    stars: [
      { x: 0.10, y: 0.50 },
      { x: 0.30, y: 0.72 },
      { x: 0.50, y: 0.45, bright: true },
      { x: 0.68, y: 0.72 },
      { x: 0.90, y: 0.52 },
    ],
    lines: [[0, 1], [1, 2], [2, 3], [3, 4]],
  },
  // 4. Cygnus — swan / Northern Cross
  {
    name_fa: "قوس",
    icon: "🦢",
    stars: [
      { x: 0.50, y: 0.10, bright: true },
      { x: 0.50, y: 0.50 },
      { x: 0.50, y: 0.90 },
      { x: 0.12, y: 0.48 },
      { x: 0.88, y: 0.52 },
    ],
    lines: [[0, 1], [1, 2], [3, 1], [1, 4]],
  },
  // 5. Lyra — the harp
  {
    name_fa: "چنگ",
    icon: "🎼",
    stars: [
      { x: 0.50, y: 0.12, bright: true },
      { x: 0.32, y: 0.42 },
      { x: 0.68, y: 0.40 },
      { x: 0.28, y: 0.78 },
      { x: 0.72, y: 0.80 },
    ],
    lines: [[0, 1], [0, 2], [1, 2], [1, 3], [2, 4], [3, 4]],
  },
  // 6. Scorpius — distinctive S-curve
  {
    name_fa: "عقرب",
    icon: "🦂",
    stars: [
      { x: 0.15, y: 0.35 },
      { x: 0.22, y: 0.48 },
      { x: 0.35, y: 0.55, bright: true },
      { x: 0.48, y: 0.62 },
      { x: 0.60, y: 0.68 },
      { x: 0.72, y: 0.68 },
      { x: 0.82, y: 0.55 },
      { x: 0.76, y: 0.40 },
    ],
    lines: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7]],
  },
  // 7. Pleiades — the Seven Sisters cluster
  {
    name_fa: "ثریا",
    icon: "✨",
    stars: [
      { x: 0.35, y: 0.35, bright: true },
      { x: 0.55, y: 0.30 },
      { x: 0.50, y: 0.48 },
      { x: 0.68, y: 0.42 },
      { x: 0.40, y: 0.58 },
      { x: 0.62, y: 0.62 },
      { x: 0.48, y: 0.72, bright: true },
    ],
    lines: [[0, 1], [1, 3], [3, 5], [5, 6], [6, 4], [4, 0]],
  },
  // 8. Sailboat
  {
    name_fa: "قایق",
    icon: "⛵",
    stars: [
      { x: 0.55, y: 0.10 },
      { x: 0.20, y: 0.62 },
      { x: 0.55, y: 0.65 },
      { x: 0.15, y: 0.78 },
      { x: 0.50, y: 0.92 },
      { x: 0.88, y: 0.78 },
    ],
    lines: [
      [0, 2],
      [0, 1], [1, 2],
      [3, 4], [4, 5],
      [3, 2], [5, 2],
    ],
  },
  // 9. Crown
  {
    name_fa: "تاج",
    icon: "👑",
    stars: [
      { x: 0.12, y: 0.68 },
      { x: 0.26, y: 0.38 },
      { x: 0.40, y: 0.55 },
      { x: 0.50, y: 0.22, bright: true },
      { x: 0.60, y: 0.55 },
      { x: 0.74, y: 0.38 },
      { x: 0.88, y: 0.68 },
    ],
    lines: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [0, 6]],
  },
  // 10. Kite
  {
    name_fa: "بادبادک",
    icon: "🪁",
    stars: [
      { x: 0.50, y: 0.10 },
      { x: 0.78, y: 0.32 },
      { x: 0.50, y: 0.55 },
      { x: 0.22, y: 0.32 },
      { x: 0.56, y: 0.70 },
      { x: 0.44, y: 0.82 },
      { x: 0.55, y: 0.92 },
    ],
    lines: [[0, 1], [1, 2], [2, 3], [3, 0], [2, 4], [4, 5], [5, 6]],
  },
  // 11. Hourglass
  {
    name_fa: "ساعت شنی",
    icon: "⏳",
    stars: [
      { x: 0.22, y: 0.12 },
      { x: 0.78, y: 0.12 },
      { x: 0.50, y: 0.50, bright: true },
      { x: 0.22, y: 0.88 },
      { x: 0.78, y: 0.88 },
    ],
    lines: [[0, 1], [0, 2], [1, 2], [2, 3], [2, 4], [3, 4]],
  },
  // 12. Cypress tree — iconic Persian secular symbol
  {
    name_fa: "سرو",
    icon: "🌲",
    stars: [
      { x: 0.50, y: 0.08, bright: true },
      { x: 0.36, y: 0.28 },
      { x: 0.64, y: 0.28 },
      { x: 0.30, y: 0.50 },
      { x: 0.70, y: 0.50 },
      { x: 0.36, y: 0.72 },
      { x: 0.64, y: 0.72 },
      { x: 0.50, y: 0.92 },
    ],
    lines: [
      [0, 1], [0, 2],
      [1, 3], [2, 4],
      [3, 5], [4, 6],
      [5, 7], [6, 7],
    ],
  },
  // 13. Butterfly
  {
    name_fa: "پروانه",
    icon: "🦋",
    stars: [
      { x: 0.50, y: 0.22 },
      { x: 0.50, y: 0.50 },
      { x: 0.50, y: 0.78 },
      { x: 0.12, y: 0.22 },
      { x: 0.88, y: 0.22 },
      { x: 0.18, y: 0.82 },
      { x: 0.82, y: 0.82 },
    ],
    lines: [
      [0, 1], [1, 2],
      [0, 3], [3, 1],
      [0, 4], [4, 1],
      [1, 5], [5, 2],
      [1, 6], [6, 2],
    ],
  },
  // 14. Tulip
  {
    name_fa: "لاله",
    icon: "🌷",
    stars: [
      { x: 0.32, y: 0.28 },
      { x: 0.50, y: 0.15, bright: true },
      { x: 0.68, y: 0.28 },
      { x: 0.35, y: 0.52 },
      { x: 0.65, y: 0.52 },
      { x: 0.50, y: 0.92 },
    ],
    lines: [
      [0, 1], [1, 2],
      [0, 3], [2, 4],
      [3, 4],
      [3, 5], [4, 5],
    ],
  },
  // 15. Bow
  {
    name_fa: "کمان",
    icon: "🏹",
    stars: [
      { x: 0.22, y: 0.12 },
      { x: 0.36, y: 0.32 },
      { x: 0.42, y: 0.50, bright: true },
      { x: 0.36, y: 0.68 },
      { x: 0.22, y: 0.88 },
      { x: 0.88, y: 0.50 },
    ],
    lines: [
      [0, 1], [1, 2], [2, 3], [3, 4],
      [0, 4],
      [2, 5],
    ],
  },
  // 16. Compass rose — 8-point navigation star
  {
    name_fa: "قطب‌نما",
    icon: "🧭",
    stars: [
      { x: 0.50, y: 0.05 },
      { x: 0.66, y: 0.34 },
      { x: 0.95, y: 0.50 },
      { x: 0.66, y: 0.66 },
      { x: 0.50, y: 0.95 },
      { x: 0.34, y: 0.66 },
      { x: 0.05, y: 0.50 },
      { x: 0.34, y: 0.34 },
      { x: 0.50, y: 0.50, bright: true },
    ],
    lines: [
      [0, 1], [1, 2], [2, 3], [3, 4],
      [4, 5], [5, 6], [6, 7], [7, 0],
    ],
  },
];

export function getTodayIcon(): string {
  return CONSTELLATIONS[seedFromDate() % CONSTELLATIONS.length].icon;
}

export function getTodayName(): string {
  return CONSTELLATIONS[seedFromDate() % CONSTELLATIONS.length].name_fa;
}

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

interface StarPath {
  x0: number; y0: number;
  mx: number; my: number;
  x: number; y: number;
  delay: number;
}

interface FieldStar {
  x: number; y: number; r: number; alpha: number; twinkleOffset: number;
}

// ─── Component ─────────────────────────────────────────

export default function DoornegarAnimation({ size = "footer" }: { size?: Size }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const startRef = useRef<number>(0);
  const formedAtRef = useRef<number>(0);
  const seedRef = useRef(seedFromDate());
  const triggeredRef = useRef(false);

  const pathsRef = useRef<StarPath[]>([]);
  const fieldStarsRef = useRef<FieldStar[]>([]);
  const constellationRef = useRef<Constellation | null>(null);
  const colorRef = useRef<string>(STAR_COLORS[0]);

  // 10s to fully form: 5.5s stars drift in, 4.5s lines connect.
  const duration = 10000;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const seed = seedRef.current;
    const constellation = CONSTELLATIONS[seed % CONSTELLATIONS.length];
    const starColor = STAR_COLORS[seed % STAR_COLORS.length];
    constellationRef.current = constellation;
    colorRef.current = starColor;

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

      pathsRef.current = constellation.stars.map((s, i) => {
        const x = bx + s.x * boxSize;
        const y = by + s.y * boxSize;
        const angle = rng() * Math.PI * 2;
        const dist = w * 0.55 + rng() * w * 0.35;
        const mx = w * 0.5 + (rng() - 0.5) * w * 0.35;
        const my = h * 0.5 + (rng() - 0.5) * h * 0.35;
        // Stagger arrivals over the first 30% of the arrival phase
        const delay = (i / constellation.stars.length) * 0.30;
        return {
          x0: w * 0.5 + Math.cos(angle) * dist,
          y0: h * 0.5 + Math.sin(angle) * dist,
          mx, my, x, y, delay,
        };
      });

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

      if (progress >= 1 && formedAtRef.current === 0) {
        formedAtRef.current = timestamp;
      }

      // ── Background field stars (fade in over first 2s) ──
      const fieldFade = Math.min(progress / 0.2, 1);
      const fieldColor = isDark ? "#ffffff" : "#334155";
      for (const fs of fieldStarsRef.current) {
        const twinkle = 0.75 + 0.25 * Math.sin(time * 1.4 + fs.twinkleOffset);
        ctx.fillStyle = hexWithAlpha(fieldColor, fs.alpha * fieldFade * twinkle);
        ctx.beginPath();
        ctx.arc(fs.x, fs.y, fs.r, 0, Math.PI * 2);
        ctx.fill();
      }

      const constellation = constellationRef.current!;
      const paths = pathsRef.current;
      const color = colorRef.current;

      // ── Phase split ──
      //   0.00 → 0.55 : stars drift in (per-star delays up to 0.30)
      //   0.55 → 1.00 : lines draw sequentially
      const STAR_PHASE_END = 0.55;

      // Current positions of each star
      const starPositions: { x: number; y: number; arrived: boolean; fadeIn: number }[] = [];

      for (let i = 0; i < constellation.stars.length; i++) {
        const p = paths[i];
        const starProgress = Math.max(
          0,
          Math.min((progress - p.delay) / Math.max(0.01, STAR_PHASE_END - p.delay), 1)
        );

        let px: number, py: number;
        if (starProgress >= 1) {
          px = p.x;
          py = p.y;
        } else {
          px = sCurve(p.x0, p.mx, p.x, starProgress);
          py = sCurve(p.y0, p.my, p.y, starProgress);
        }

        // Fade in over the first 20% of each star's individual arrival
        const fadeIn = Math.min(starProgress / 0.2, 1);
        starPositions.push({ x: px, y: py, arrived: starProgress >= 1, fadeIn });
      }

      // ── Draw connecting lines ──
      const linePhase = Math.max(0, Math.min((progress - STAR_PHASE_END) / (1 - STAR_PHASE_END), 1));
      const totalLines = constellation.lines.length;

      for (let li = 0; li < totalLines; li++) {
        const [a, b] = constellation.lines[li];
        const posA = starPositions[a];
        const posB = starPositions[b];
        if (!posA.arrived || !posB.arrived) continue;

        const slotStart = li / totalLines;
        const slotEnd = (li + 1) / totalLines;
        const lineProgress = Math.max(
          0,
          Math.min((linePhase - slotStart) / (slotEnd - slotStart), 1)
        );
        if (lineProgress <= 0) continue;

        const ex = posA.x + (posB.x - posA.x) * lineProgress;
        const ey = posA.y + (posB.y - posA.y) * lineProgress;

        ctx.beginPath();
        ctx.moveTo(posA.x, posA.y);
        ctx.lineTo(ex, ey);
        ctx.strokeStyle = hexWithAlpha(color, 0.40);
        ctx.lineWidth = 0.8;
        ctx.lineCap = "round";
        ctx.stroke();
      }

      // ── Draw stars (with glow + post-formation twinkle) ──
      for (let i = 0; i < constellation.stars.length; i++) {
        const starDef = constellation.stars[i];
        const pos = starPositions[i];

        const baseR = starDef.bright ? 2.2 : 1.5;
        const glowR = starDef.bright ? 5.5 : 3.5;

        // Post-formation twinkle: gentle sinusoidal brightness shimmer
        const twinkle = formedAtRef.current > 0
          ? 0.82 + 0.18 * Math.sin(time * 1.8 + i * 1.37)
          : 1.0;
        const alpha = pos.fadeIn * twinkle;

        // Glow halo
        const glow = ctx.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, glowR);
        glow.addColorStop(0, hexWithAlpha(color, 0.38 * alpha));
        glow.addColorStop(1, hexWithAlpha(color, 0));
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, glowR, 0, Math.PI * 2);
        ctx.fill();

        // Core
        ctx.fillStyle = hexWithAlpha(color, alpha);
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, baseR, 0, Math.PI * 2);
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
        aria-label={`صورت فلکی امروز: ${name}`}
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
