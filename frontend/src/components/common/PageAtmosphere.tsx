"use client";

import { useEffect } from "react";

/*
  PageAtmosphere — ambient effects for the whole page:
  1. Staggered scroll entrance (elements fade+slide up as you scroll)
  2. Parallax depth (images move slower than text on scroll)
  3. Smooth scroll momentum (CSS smooth scroll)
*/

export default function PageAtmosphere() {
  useEffect(() => {
    // ─── 1. Staggered scroll entrance ─────────────────────
    const observerEntrance = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry, i) => {
          if (entry.isIntersecting) {
            const el = entry.target as HTMLElement;
            // Stagger delay based on position among siblings
            const siblings = el.parentElement?.children;
            let idx = 0;
            if (siblings) {
              for (let j = 0; j < siblings.length; j++) {
                if (siblings[j] === el) { idx = j; break; }
              }
            }
            const delay = idx * 80;
            setTimeout(() => {
              el.style.opacity = "1";
              el.style.transform = "translateY(0)";
            }, delay);
            observerEntrance.unobserve(el);
          }
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -40px 0px" }
    );

    // Apply to story cards below the fold (limit to first 30 elements)
    const candidates = document.querySelectorAll("main a.group, main .grid > a");
    const limited = Array.from(candidates).slice(0, 30);
    limited.forEach((el) => {
      const htmlEl = el as HTMLElement;
      // Skip if already visible (above fold)
      const rect = htmlEl.getBoundingClientRect();
      if (rect.top < window.innerHeight) return;
      htmlEl.style.opacity = "0";
      htmlEl.style.transform = "translateY(20px)";
      htmlEl.style.transition = "opacity 0.6s ease, transform 0.6s ease";
      observerEntrance.observe(htmlEl);
    });

    // ─── 2. Parallax depth (images only, inside overflow:hidden containers) ──
    let ticking = false;
    const parallaxImages: HTMLElement[] = [];

    document.querySelectorAll("[dir='rtl'] .aspect-\\[16\\/10\\] img, [dir='rtl'] .aspect-\\[4\\/3\\] img").forEach((el) => {
      const htmlEl = el as HTMLElement;
      htmlEl.style.willChange = "transform";
      htmlEl.style.transform = "scale(1.03)";
      htmlEl.style.transition = "transform 0.4s ease-out";
      parallaxImages.push(htmlEl);
    });

    const handleScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        parallaxImages.forEach((el) => {
          const rect = el.getBoundingClientRect();
          const center = rect.top + rect.height / 2;
          const viewCenter = window.innerHeight / 2;
          const offset = (center - viewCenter) * 0.02;
          el.style.transform = `translateY(${offset}px) scale(1.03)`;
        });
        ticking = false;
      });
    };

    window.addEventListener("scroll", handleScroll, { passive: true });

    const root = document.documentElement;

    // ─── 3. Smooth scroll momentum ────────────────────────
    root.style.scrollBehavior = "smooth";

    // Cleanup
    return () => {
      observerEntrance.disconnect();
      window.removeEventListener("scroll", handleScroll);
      root.style.scrollBehavior = "";
    };
  }, []);

  return null; // No visual output — all effects are imperative
}
