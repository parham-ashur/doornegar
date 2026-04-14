"use client";

import { useEffect, useRef } from "react";

// 50 micro pixel art objects
const OBJECTS: { dx: number; dy: number; c: number }[][] = [
  [{dx:0,dy:1,c:0},{dx:1,dy:0,c:0},{dx:2,dy:0,c:0},{dx:3,dy:1,c:0},{dx:0,dy:2,c:1},{dx:3,dy:2,c:1},{dx:1,dy:3,c:0},{dx:2,dy:3,c:0},{dx:4,dy:1,c:1},{dx:5,dy:0,c:1},{dx:6,dy:0,c:1},{dx:7,dy:1,c:1},{dx:4,dy:2,c:0},{dx:7,dy:2,c:0},{dx:5,dy:3,c:1},{dx:6,dy:3,c:1}],
  [{dx:1,dy:0,c:0},{dx:2,dy:0,c:0},{dx:0,dy:1,c:0},{dx:3,dy:1,c:1},{dx:0,dy:2,c:0},{dx:1,dy:2,c:1},{dx:2,dy:2,c:1},{dx:3,dy:2,c:1},{dx:4,dy:1,c:0},{dx:5,dy:0,c:1},{dx:6,dy:1,c:1},{dx:5,dy:2,c:0},{dx:6,dy:2,c:1},{dx:4,dy:2,c:0}],
  [{dx:2,dy:0,c:0},{dx:1,dy:1,c:0},{dx:2,dy:1,c:1},{dx:3,dy:1,c:0},{dx:0,dy:2,c:1},{dx:1,dy:2,c:0},{dx:2,dy:2,c:1},{dx:3,dy:2,c:0},{dx:4,dy:2,c:1},{dx:0,dy:3,c:1},{dx:1,dy:3,c:0},{dx:2,dy:3,c:0},{dx:3,dy:3,c:0},{dx:4,dy:3,c:1}],
  [{dx:1,dy:0,c:0},{dx:0,dy:1,c:1},{dx:1,dy:1,c:0},{dx:2,dy:1,c:1},{dx:3,dy:1,c:0},{dx:4,dy:2,c:1},{dx:1,dy:2,c:0},{dx:2,dy:2,c:1},{dx:3,dy:2,c:0}],
  [{dx:2,dy:0,c:1},{dx:1,dy:1,c:0},{dx:2,dy:1,c:1},{dx:3,dy:1,c:0},{dx:0,dy:2,c:1},{dx:1,dy:2,c:0},{dx:2,dy:2,c:1},{dx:3,dy:2,c:0},{dx:4,dy:2,c:1},{dx:1,dy:3,c:0},{dx:2,dy:3,c:1},{dx:3,dy:3,c:0},{dx:2,dy:4,c:1}],
  [{dx:1,dy:0,c:1},{dx:3,dy:0,c:0},{dx:0,dy:1,c:1},{dx:1,dy:1,c:0},{dx:2,dy:1,c:1},{dx:3,dy:1,c:0},{dx:4,dy:1,c:1},{dx:0,dy:2,c:0},{dx:1,dy:2,c:1},{dx:2,dy:2,c:0},{dx:3,dy:2,c:1},{dx:4,dy:2,c:0},{dx:1,dy:3,c:1},{dx:2,dy:3,c:0},{dx:3,dy:3,c:1},{dx:2,dy:4,c:0}],
  [{dx:2,dy:0,c:0},{dx:1,dy:1,c:0},{dx:2,dy:1,c:1},{dx:3,dy:1,c:0},{dx:0,dy:2,c:1},{dx:1,dy:2,c:0},{dx:2,dy:2,c:1},{dx:3,dy:2,c:0},{dx:4,dy:2,c:1},{dx:2,dy:3,c:0},{dx:2,dy:4,c:1}],
  [{dx:0,dy:0,c:0},{dx:1,dy:0,c:1},{dx:2,dy:0,c:0},{dx:0,dy:1,c:1},{dx:1,dy:1,c:0},{dx:2,dy:1,c:1},{dx:3,dy:1,c:0},{dx:0,dy:2,c:0},{dx:1,dy:2,c:1},{dx:2,dy:2,c:0},{dx:3,dy:2,c:1},{dx:0,dy:3,c:1},{dx:1,dy:3,c:0},{dx:2,dy:3,c:1}],
  [{dx:0,dy:0,c:0},{dx:0,dy:1,c:0},{dx:0,dy:2,c:0},{dx:0,dy:3,c:0},{dx:0,dy:4,c:0},{dx:1,dy:0,c:1},{dx:2,dy:0,c:0},{dx:3,dy:0,c:1},{dx:1,dy:1,c:0},{dx:2,dy:1,c:1},{dx:3,dy:1,c:0}],
  [{dx:2,dy:0,c:0},{dx:1,dy:1,c:1},{dx:2,dy:1,c:0},{dx:3,dy:1,c:1},{dx:0,dy:2,c:0},{dx:2,dy:2,c:1},{dx:4,dy:2,c:0},{dx:2,dy:3,c:0},{dx:2,dy:4,c:1}],
  [{dx:1,dy:0,c:1},{dx:2,dy:0,c:0},{dx:0,dy:1,c:0},{dx:0,dy:2,c:1},{dx:0,dy:3,c:0},{dx:1,dy:4,c:1},{dx:2,dy:4,c:0},{dx:3,dy:1,c:1},{dx:3,dy:3,c:1}],
  [{dx:2,dy:0,c:1},{dx:0,dy:2,c:0},{dx:1,dy:1,c:0},{dx:2,dy:1,c:1},{dx:3,dy:1,c:0},{dx:1,dy:2,c:1},{dx:2,dy:2,c:0},{dx:3,dy:2,c:1},{dx:1,dy:3,c:0},{dx:2,dy:3,c:1},{dx:3,dy:3,c:0},{dx:4,dy:2,c:1},{dx:2,dy:4,c:0}],
  [{dx:2,dy:0,c:0},{dx:1,dy:1,c:1},{dx:3,dy:1,c:1},{dx:0,dy:2,c:0},{dx:4,dy:2,c:0},{dx:1,dy:3,c:1},{dx:3,dy:3,c:1},{dx:2,dy:4,c:0}],
  [{dx:0,dy:0,c:0},{dx:1,dy:0,c:1},{dx:0,dy:1,c:1},{dx:1,dy:1,c:0},{dx:2,dy:1,c:1},{dx:3,dy:1,c:0},{dx:4,dy:1,c:1},{dx:5,dy:1,c:0},{dx:5,dy:2,c:1},{dx:3,dy:2,c:0}],
  [{dx:2,dy:0,c:0},{dx:2,dy:1,c:1},{dx:0,dy:2,c:0},{dx:1,dy:2,c:1},{dx:2,dy:2,c:0},{dx:3,dy:2,c:1},{dx:4,dy:2,c:0},{dx:1,dy:3,c:1},{dx:2,dy:3,c:0},{dx:3,dy:3,c:1}],
  [{dx:1,dy:0,c:0},{dx:0,dy:1,c:1},{dx:1,dy:1,c:0},{dx:2,dy:1,c:1},{dx:1,dy:2,c:0}],
  [{dx:0,dy:1,c:0},{dx:1,dy:0,c:1},{dx:1,dy:1,c:0},{dx:1,dy:2,c:1},{dx:2,dy:1,c:0},{dx:3,dy:0,c:1},{dx:3,dy:1,c:0},{dx:3,dy:2,c:1},{dx:4,dy:1,c:0}],
  [{dx:1,dy:0,c:0},{dx:2,dy:0,c:1},{dx:0,dy:1,c:0},{dx:1,dy:1,c:1},{dx:2,dy:1,c:0},{dx:3,dy:1,c:1},{dx:0,dy:2,c:1},{dx:1,dy:2,c:0},{dx:2,dy:2,c:1},{dx:3,dy:2,c:0}],
  [{dx:1,dy:0,c:1},{dx:2,dy:0,c:0},{dx:3,dy:0,c:1},{dx:0,dy:1,c:0},{dx:4,dy:1,c:0},{dx:2,dy:2,c:0},{dx:2,dy:3,c:1},{dx:1,dy:4,c:0}],
  [{dx:2,dy:0,c:0},{dx:1,dy:1,c:1},{dx:3,dy:1,c:1},{dx:0,dy:2,c:0},{dx:4,dy:2,c:0},{dx:2,dy:3,c:1}],
  [{dx:2,dy:0,c:0},{dx:1,dy:1,c:1},{dx:2,dy:1,c:0},{dx:3,dy:1,c:1},{dx:0,dy:2,c:0},{dx:1,dy:2,c:1},{dx:2,dy:2,c:0},{dx:3,dy:2,c:1},{dx:4,dy:2,c:0}],
  [{dx:0,dy:0,c:1},{dx:2,dy:0,c:0},{dx:4,dy:0,c:1},{dx:0,dy:1,c:0},{dx:1,dy:1,c:1},{dx:2,dy:1,c:0},{dx:3,dy:1,c:1},{dx:4,dy:1,c:0},{dx:0,dy:2,c:1},{dx:1,dy:2,c:0},{dx:2,dy:2,c:1},{dx:3,dy:2,c:0},{dx:4,dy:2,c:1}],
  [{dx:1,dy:0,c:0},{dx:2,dy:0,c:1},{dx:0,dy:1,c:0},{dx:3,dy:1,c:1},{dx:0,dy:2,c:1},{dx:1,dy:2,c:0},{dx:2,dy:2,c:1},{dx:3,dy:2,c:0},{dx:0,dy:3,c:0},{dx:1,dy:3,c:1},{dx:2,dy:3,c:0},{dx:3,dy:3,c:1}],
  [{dx:3,dy:0,c:0},{dx:3,dy:1,c:1},{dx:2,dy:1,c:0},{dx:3,dy:2,c:0},{dx:0,dy:3,c:1},{dx:1,dy:3,c:0},{dx:0,dy:2,c:1}],
  [{dx:0,dy:0,c:0},{dx:1,dy:0,c:1},{dx:2,dy:0,c:0},{dx:3,dy:0,c:1},{dx:0,dy:1,c:1},{dx:3,dy:1,c:0},{dx:0,dy:2,c:0},{dx:3,dy:2,c:1},{dx:0,dy:3,c:1},{dx:1,dy:3,c:0},{dx:2,dy:3,c:1},{dx:3,dy:3,c:0}],
  [{dx:1,dy:0,c:0},{dx:2,dy:0,c:1},{dx:0,dy:1,c:1},{dx:3,dy:1,c:0},{dx:1,dy:2,c:0},{dx:2,dy:2,c:1}],
  [{dx:0,dy:0,c:1},{dx:1,dy:1,c:0},{dx:2,dy:2,c:1},{dx:3,dy:3,c:0},{dx:4,dy:4,c:1}],
  [{dx:0,dy:1,c:0},{dx:1,dy:0,c:1},{dx:2,dy:1,c:0},{dx:3,dy:0,c:1},{dx:4,dy:1,c:0}],
  [{dx:0,dy:0,c:0},{dx:1,dy:0,c:1},{dx:2,dy:1,c:0},{dx:1,dy:2,c:1},{dx:0,dy:2,c:0}],
  [{dx:2,dy:0,c:1},{dx:1,dy:1,c:0},{dx:3,dy:1,c:0},{dx:0,dy:2,c:1},{dx:4,dy:2,c:1},{dx:1,dy:3,c:0},{dx:3,dy:3,c:0},{dx:2,dy:4,c:1}],
  [{dx:0,dy:0,c:0},{dx:1,dy:0,c:1},{dx:2,dy:0,c:0},{dx:0,dy:1,c:1},{dx:2,dy:1,c:1},{dx:0,dy:2,c:0},{dx:1,dy:2,c:1},{dx:2,dy:2,c:0}],
  [{dx:0,dy:2,c:0},{dx:1,dy:1,c:1},{dx:2,dy:0,c:0},{dx:3,dy:0,c:1},{dx:4,dy:1,c:0},{dx:5,dy:2,c:1}],
  [{dx:1,dy:0,c:0},{dx:0,dy:1,c:1},{dx:2,dy:1,c:1},{dx:1,dy:2,c:0},{dx:0,dy:3,c:1},{dx:2,dy:3,c:1},{dx:1,dy:4,c:0}],
  [{dx:0,dy:0,c:0},{dx:1,dy:0,c:1},{dx:0,dy:1,c:1},{dx:1,dy:1,c:0}],
  [{dx:0,dy:0,c:1},{dx:1,dy:1,c:0},{dx:0,dy:2,c:1},{dx:1,dy:3,c:0}],
  [{dx:0,dy:0,c:0},{dx:1,dy:0,c:1},{dx:2,dy:0,c:0},{dx:3,dy:0,c:1},{dx:4,dy:0,c:0}],
  [{dx:0,dy:0,c:0},{dx:2,dy:0,c:1},{dx:4,dy:0,c:0},{dx:1,dy:1,c:1},{dx:3,dy:1,c:0}],
  [{dx:0,dy:0,c:1},{dx:1,dy:0,c:0},{dx:2,dy:0,c:1},{dx:0,dy:1,c:0},{dx:2,dy:1,c:0},{dx:0,dy:2,c:1},{dx:1,dy:2,c:0},{dx:2,dy:2,c:1},{dx:1,dy:1,c:1}],
  [{dx:2,dy:0,c:0},{dx:3,dy:0,c:1},{dx:1,dy:1,c:0},{dx:4,dy:1,c:1},{dx:0,dy:2,c:0},{dx:5,dy:2,c:1},{dx:1,dy:4,c:1},{dx:4,dy:4,c:0},{dx:2,dy:5,c:1},{dx:3,dy:5,c:0}],
  [{dx:0,dy:1,c:0},{dx:1,dy:0,c:1},{dx:2,dy:0,c:0},{dx:3,dy:1,c:1},{dx:0,dy:2,c:0},{dx:1,dy:3,c:1},{dx:2,dy:3,c:0},{dx:3,dy:2,c:1}],
  [{dx:1,dy:0,c:0},{dx:0,dy:1,c:1},{dx:1,dy:1,c:0},{dx:2,dy:1,c:1},{dx:1,dy:2,c:0},{dx:3,dy:0,c:1},{dx:3,dy:2,c:0},{dx:4,dy:1,c:1}],
  [{dx:0,dy:0,c:1},{dx:1,dy:0,c:0},{dx:2,dy:1,c:1},{dx:1,dy:2,c:0},{dx:0,dy:2,c:1},{dx:0,dy:1,c:0}],
  [{dx:0,dy:0,c:0},{dx:4,dy:0,c:1},{dx:1,dy:1,c:1},{dx:3,dy:1,c:0},{dx:2,dy:2,c:0},{dx:2,dy:3,c:1}],
  [{dx:2,dy:0,c:1},{dx:1,dy:1,c:0},{dx:3,dy:1,c:0},{dx:0,dy:2,c:1},{dx:2,dy:2,c:0},{dx:4,dy:2,c:1}],
  [{dx:0,dy:0,c:0},{dx:1,dy:0,c:1},{dx:2,dy:0,c:0},{dx:2,dy:1,c:1},{dx:2,dy:2,c:0},{dx:1,dy:2,c:1},{dx:0,dy:2,c:0},{dx:0,dy:1,c:1}],
  [{dx:1,dy:0,c:0},{dx:0,dy:1,c:1},{dx:2,dy:1,c:0},{dx:0,dy:2,c:0},{dx:1,dy:2,c:1},{dx:2,dy:2,c:0},{dx:3,dy:2,c:1}],
  [{dx:0,dy:0,c:1},{dx:1,dy:0,c:0},{dx:2,dy:0,c:1},{dx:3,dy:0,c:0},{dx:1,dy:1,c:1},{dx:2,dy:1,c:0}],
  [{dx:0,dy:0,c:0},{dx:1,dy:0,c:1},{dx:2,dy:0,c:0},{dx:0,dy:1,c:1},{dx:1,dy:1,c:0},{dx:2,dy:1,c:1}],
  [{dx:0,dy:0,c:1},{dx:2,dy:0,c:0},{dx:1,dy:1,c:1},{dx:0,dy:2,c:0},{dx:2,dy:2,c:1},{dx:1,dy:3,c:0}],
  [{dx:1,dy:0,c:0},{dx:0,dy:1,c:1},{dx:2,dy:1,c:0},{dx:1,dy:2,c:1},{dx:0,dy:3,c:0},{dx:2,dy:3,c:1}],
];

const BLUE = "#1e3a5f";
const ORANGE = "#ea580c";
const BLUE_DARK = "#3b82f6";
const PX = 3;

// Seasonal theme
function getSeason() {
  const m = new Date().getMonth();
  if (m >= 2 && m <= 4) return { glow: "#10b981", trail: "#6ee7b7" }; // Spring
  if (m >= 5 && m <= 7) return { glow: "#f59e0b", trail: "#fcd34d" }; // Summer
  if (m >= 8 && m <= 10) return { glow: "#dc2626", trail: "#fca5a5" }; // Autumn
  return { glow: "#3b82f6", trail: "#93c5fd" }; // Winter
}

interface DunePixel { x: number; y: number; vy: number; color: string; settled: boolean }
interface FlyingPixel { sx: number; sy: number; tx: number; ty: number; wx: number; wy: number; color: string; t: number; delay: number }
interface Trail { x: number; y: number; color: string; life: number }
interface Bot { x: number; y: number; tx: number; ty: number; color: string; frame: number; speed: number; kind: "busy"|"lazy"|"erratic"; rest: number; carrying: boolean; carryColor: string }
interface Done { pixels: {x:number;y:number;color:string}[]; sx: number }

export default function HeaderAnimation() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const parent = canvas.parentElement;
    if (!parent) return;

    const dpr = window.devicePixelRatio || 1;
    let W = parent.clientWidth;
    let H = parent.clientHeight;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
    const ctx = canvas.getContext("2d")!;
    ctx.scale(dpr, dpr);

    const dark = () => window.matchMedia("(prefers-color-scheme: dark)").matches;
    const season = getSeason();

    // Shuffle helper
    function shuf(n: number) { const a = Array.from({length:n},(_,i)=>i); for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]];} return a; }

    // State
    let stage: "pouring" | "workers_enter" | "building" | "holding" | "sliding" = "pouring";
    let stageStart = 0;
    const duneBlue: DunePixel[] = [];
    const duneOrange: DunePixel[] = [];
    let flyPixels: FlyingPixel[] = [];
    let trails: Trail[] = [];
    let bots: Bot[] = [];
    let done: Done[] = [];
    let objQ = shuf(OBJECTS.length);
    let objI = 0;
    let pourCount = 0;

    // Dune positions
    const duneBlueX = () => W - 10;
    const duneOrangeX = () => W - 30;

    function pourPixel(color: string, baseX: number) {
      return { x: baseX + (Math.random()-0.5)*8, y: -2 - Math.random()*5, vy: 0.4 + Math.random()*0.3, color, settled: false };
    }

    function initBots() {
      const d = dark();
      const kinds: Bot["kind"][] = ["busy","lazy","erratic","busy","erratic"];
      const count = 3 + Math.floor(Math.random()*2);
      bots = [];
      for (let i = 0; i < count; i++) {
        const isB = i % 2 === 0;
        const k = kinds[i % kinds.length];
        bots.push({ x: W + 5 + i*8, y: H/2 + (Math.random()-0.5)*10, tx: W-50, ty: H/2, color: isB ? (d?BLUE_DARK:BLUE) : ORANGE, frame: Math.floor(Math.random()*100), speed: k==="busy"?0.6:k==="lazy"?0.2:0.45, kind: k, rest: 0, carrying: false, carryColor: "" });
      }
    }

    function nextObj() {
      if (objI >= objQ.length) { objQ = shuf(OBJECTS.length); objI = 0; }
      const obj = OBJECTS[objQ[objI++]];
      const d = dark();
      const objW = (Math.max(...obj.map(p=>p.dx))+1)*(PX+1);
      const objH = (Math.max(...obj.map(p=>p.dy))+1)*(PX+1);
      const bx = W - 60 - objW;
      const by = (H - objH) / 2;

      flyPixels = obj.map((p, i) => {
        const isB = p.c === 0;
        const duneX = isB ? duneBlueX() : duneOrangeX();
        return { sx: duneX + (Math.random()-0.5)*6, sy: H - 3 - Math.random()*8, tx: bx + p.dx*(PX+1), ty: by + p.dy*(PX+1), wx: (Math.random()-0.5)*20, wy: (Math.random()-0.5)*12, color: isB?(d?BLUE_DARK:BLUE):ORANGE, t: 0, delay: i*180 + Math.random()*300 };
      });
      stage = "building";
      stageStart = performance.now();
    }

    function drawBot(b: Bot) {
      const d = dark();
      const bc = d ? "#94a3b8" : "#64748b";
      // Body — larger (5x4)
      ctx.fillStyle = bc;
      ctx.fillRect(b.x-2, b.y-2, 5, 4);
      // Head
      ctx.fillStyle = b.color;
      ctx.fillRect(b.x-1, b.y-3, 3, 1);
      // Eyes
      ctx.fillStyle = d ? "#0a0e1a" : "#ffffff";
      ctx.fillRect(b.x-1, b.y-3, 1, 1);
      ctx.fillRect(b.x+1, b.y-3, 1, 1);
      // Wings
      const flap = Math.sin(b.frame * 0.25) * 2;
      ctx.fillStyle = bc;
      ctx.globalAlpha = 0.4;
      ctx.fillRect(b.x-3, b.y-1+flap, 1, 2);
      ctx.fillRect(b.x+3, b.y-1-flap, 1, 2);
      ctx.globalAlpha = 1;
      // Carrying pixel
      if (b.carrying) {
        ctx.fillStyle = b.carryColor;
        ctx.fillRect(b.x-1, b.y+2, PX, PX);
      }
      // Lazy bot: zzz
      if (b.kind === "lazy" && b.rest > 0) {
        ctx.fillStyle = d ? "#475569" : "#cbd5e1";
        ctx.globalAlpha = 0.5;
        ctx.fillText("z", b.x+3, b.y-3);
        ctx.globalAlpha = 1;
      }
    }

    function updateBots() {
      for (const b of bots) {
        b.frame++;
        if (b.kind === "lazy" && b.rest > 0) { b.rest--; continue; }
        if (b.kind === "lazy" && Math.random() < 0.003) b.rest = 80 + Math.floor(Math.random()*60);

        const dx = b.tx - b.x; const dy = b.ty - b.y;
        const dist = Math.sqrt(dx*dx + dy*dy);
        if (dist > 1.5) {
          let mx = (dx/dist)*b.speed;
          let my = (dy/dist)*b.speed;
          if (b.kind === "erratic") { mx += Math.sin(b.frame*0.15)*1; my += Math.cos(b.frame*0.12)*0.8; }
          b.x += mx + (Math.random()-0.5)*0.3;
          b.y += my + (Math.random()-0.5)*0.3;
        } else {
          const range = b.kind === "busy" ? 50 : b.kind === "lazy" ? 15 : 35;
          b.tx = W - 30 - Math.random()*range;
          b.ty = 3 + Math.random()*(H-8);
        }
        b.x = Math.max(W-100, Math.min(W-3, b.x));
        b.y = Math.max(3, Math.min(H-4, b.y));
      }
    }

    function draw(now: number) {
      const d = dark();
      ctx.clearRect(0, 0, W, H);

      // === STAGE: Pouring — create dune mountains ===
      if (stage === "pouring") {
        const elapsed = now - stageStart;
        // Pour blue pixels
        if (pourCount % 3 === 0 && duneBlue.length < 25) duneBlue.push(pourPixel(d?BLUE_DARK:BLUE, duneBlueX()));
        if (pourCount % 3 === 1 && duneOrange.length < 25) duneOrange.push(pourPixel(ORANGE, duneOrangeX()));
        pourCount++;

        // Settle dune pixels
        for (const dp of [...duneBlue, ...duneOrange]) {
          if (!dp.settled) {
            dp.y += dp.vy;
            dp.vy += 0.08;
            if (dp.y >= H - 2) { dp.y = H - 2 - Math.random()*2; dp.settled = true; }
            // Stack on other settled pixels in same column
            const col = Math.round(dp.x);
            const same = [...duneBlue,...duneOrange].filter(o => o.settled && Math.abs(Math.round(o.x)-col) < 3 && o !== dp);
            if (same.length > 0) {
              const topY = Math.min(...same.map(s=>s.y));
              if (dp.y >= topY - 2) { dp.y = topY - 2 - Math.random(); dp.settled = true; }
            }
          }
        }

        if (elapsed > 3000) { stage = "workers_enter"; stageStart = now; initBots(); }
      }

      // === STAGE: Workers fly in ===
      if (stage === "workers_enter") {
        updateBots();
        if (now - stageStart > 2000) { nextObj(); }
      }

      // === Draw dune pixels always ===
      for (const dp of [...duneBlue, ...duneOrange]) {
        ctx.fillStyle = dp.color;
        ctx.globalAlpha = dp.settled ? 0.35 : 0.6;
        ctx.fillRect(dp.x, dp.y, 2, 2);
      }
      ctx.globalAlpha = 1;

      // === Draw + fade trails ===
      trails = trails.filter(t => t.life > 0);
      for (const t of trails) {
        t.life -= 0.025;
        ctx.fillStyle = t.color;
        ctx.globalAlpha = t.life * 0.35;
        ctx.fillRect(t.x, t.y, 1, 1);
      }
      ctx.globalAlpha = 1;

      // === BUILDING: Pixels fly from dunes to target ===
      if (stage === "building") {
        const elapsed = now - stageStart;
        const dur = 7000;
        let allDone = true;

        for (const p of flyPixels) {
          const t = Math.max(0, Math.min(1, (elapsed - p.delay) / 3000));
          p.t = t;
          if (t < 1) allDone = false;

          const ease = 1 - Math.pow(1-t, 3);
          const midX = (p.sx+p.tx)/2 + p.wx;
          const midY = Math.min(p.sy,p.ty) - 10 + p.wy;
          const mt = 1 - ease;
          const x = mt*mt*p.sx + 2*mt*ease*midX + ease*ease*p.tx;
          const y = mt*mt*p.sy + 2*mt*ease*midY + ease*ease*p.ty;

          // Trail
          if (t > 0.05 && t < 0.9 && Math.random() < 0.25) {
            trails.push({ x: x+(Math.random()-0.5)*3, y: y+(Math.random()-0.5)*3, color: season.trail, life: 0.7+Math.random()*0.3 });
          }

          ctx.fillStyle = p.color;
          ctx.globalAlpha = Math.min(1, t*3);
          ctx.fillRect(x, y, PX, PX);
        }
        ctx.globalAlpha = 1;

        // Make bots look like they're carrying — closest bot to each active pixel
        for (const b of bots) {
          const active = flyPixels.filter(p => p.t > 0.1 && p.t < 0.8);
          if (active.length > 0) {
            const nearest = active.reduce((a,c) => {
              const da = Math.hypot(a.sx+(a.tx-a.sx)*a.t-b.x, a.sy+(a.ty-a.sy)*a.t-b.y);
              const dc = Math.hypot(c.sx+(c.tx-c.sx)*c.t-b.x, c.sy+(c.ty-c.sy)*c.t-b.y);
              return dc < da ? c : a;
            });
            b.tx = nearest.sx + (nearest.tx-nearest.sx)*nearest.t + (Math.random()-0.5)*8;
            b.ty = nearest.sy + (nearest.ty-nearest.sy)*nearest.t + (Math.random()-0.5)*8;
            b.carrying = true;
            b.carryColor = nearest.color;
          } else {
            b.carrying = false;
          }
        }
        updateBots();

        if (allDone && elapsed > dur) { stage = "holding"; stageStart = now; for (const b of bots) b.carrying = false; }
      }

      // === HOLDING ===
      if (stage === "holding") {
        const gt = (now - stageStart) / 1000;
        const ga = 0.06 + Math.sin(gt*2)*0.03;
        ctx.fillStyle = season.glow;
        ctx.globalAlpha = ga;
        const mnX = Math.min(...flyPixels.map(p=>p.tx))-2;
        const mnY = Math.min(...flyPixels.map(p=>p.ty))-2;
        const mxX = Math.max(...flyPixels.map(p=>p.tx))+PX+2;
        const mxY = Math.max(...flyPixels.map(p=>p.ty))+PX+2;
        ctx.fillRect(mnX,mnY,mxX-mnX,mxY-mnY);
        ctx.globalAlpha = 1;

        for (const p of flyPixels) { ctx.fillStyle = p.color; ctx.fillRect(p.tx,p.ty,PX,PX); }
        updateBots();

        if (now - stageStart > 2500) {
          done.push({ pixels: flyPixels.map(p=>({x:p.tx,y:p.ty,color:p.color})), sx: 0 });
          if (done.length > 4) done.shift();
          stage = "sliding"; stageStart = now;
        }
      }

      // === SLIDING ===
      if (stage === "sliding") {
        const se = now - stageStart;
        const sd = 1200;
        const sp = Math.min(1, se/sd);
        const sEase = 1-Math.pow(1-sp,2);
        for (const o of done) o.sx = -55 * sEase;

        if (se > sd) {
          for (const o of done) { for (const p of o.pixels) p.x += o.sx; o.sx = 0; }
          done = done.filter(o => o.pixels.some(p => p.x > -10));
          updateBots();
          nextObj();
        }
      }

      // === Draw completed objects ===
      for (const o of done) {
        for (const p of o.pixels) { ctx.fillStyle = p.color; ctx.globalAlpha = 0.35; ctx.fillRect(p.x+o.sx,p.y,PX,PX); }
      }
      ctx.globalAlpha = 1;

      // === Draw bots (always, once entered) ===
      if (stage !== "pouring") {
        for (const b of bots) drawBot(b);
      }

      animRef.current = requestAnimationFrame(draw);
    }

    // Start with pouring phase after logo animation
    const timer = setTimeout(() => {
      stageStart = performance.now();
      animRef.current = requestAnimationFrame(draw);
    }, 3500);

    const ro = new ResizeObserver(() => {
      W = parent.clientWidth; H = parent.clientHeight;
      canvas.width = W*dpr; canvas.height = H*dpr;
      canvas.style.width = W+"px"; canvas.style.height = H+"px";
      ctx.setTransform(1,0,0,1,0,0); ctx.scale(dpr,dpr);
    });
    ro.observe(parent);

    return () => { clearTimeout(timer); cancelAnimationFrame(animRef.current); ro.disconnect(); };
  }, []);

  return (
    <div className="flex-1 hidden sm:block h-[40px] overflow-hidden mx-6">
      <canvas ref={canvasRef} className="w-full h-full" />
    </div>
  );
}
