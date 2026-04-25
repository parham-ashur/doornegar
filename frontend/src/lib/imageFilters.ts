// URL-level filters and resolvers for article/story images. Shared by
// the client `SafeImage` (with runtime onError fallback) and the server
// `SafeImageStatic` (used on homepage cards where the JS for runtime
// fallback isn't worth a hydration boundary).

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Icons / app-icons that the ingester sometimes picks up when no real
// og:image is present (radiofarda, some Iranian sites that only return
// a favicon-sized icon). They pass MIN_WIDTH but look like placeholders.
const ICON_URL_PATTERNS = [
  /\/ico-\d+x\d+\.(png|jpg|webp|svg)(\?|$)/i,
  /\/favicon[.\-]/i,
  /\/icon[.\-]\d+/i,
  /\/apple-touch-icon/i,
  /\/webApp\/ico-/i,
  /\/manifest-icon/i,
];

// Iran-hosted media that geo-block Vercel's US/EU edge IPs. Vercel's
// `/_next/image` proxy-fetches the source from its own servers to
// optimize; when the source blocks Vercel, the endpoint returns a
// 400 and the image renders as a placeholder even though users can
// reach it directly from their browsers. For these hostnames we
// bypass Vercel's optimizer.
const GEOBLOCKED_FROM_VERCEL = [
  "irna.ir",
  "tasnimnews.com",
  "farsnews.ir",
  "farsnews.com",
  "mehrnews.com",
  "mashreghnews.ir",
  "nournews.ir",
  "iribnews.ir",
  "isna.ir",
  "etemadnewspaper.ir",
  "khabaronline.ir",
  "yjc.ir",
  "tabnak.ir",
  "asriran.com",
  "sharghdaily.com",
  "ilna.ir",
  "entekhab.ir",
  "rajanews.com",
  "hamshahrionline.ir",
];

export function isLikelyIcon(src: string): boolean {
  return ICON_URL_PATTERNS.some((re) => re.test(src));
}

// Iran International's Sanity CDN returns 400 "Invalid filename" when
// the bare image hash is requested without a transform+extension
// suffix like `-800x531.jpg`. Detect and reject up front.
export function isBrokenIranInternationalUrl(src: string): boolean {
  try {
    const u = new URL(src);
    if (u.hostname !== "i.iranintl.com") return false;
    return !/-\d+x\d+\.(jpg|jpeg|png|webp)(\?|$)/i.test(u.pathname);
  } catch {
    return false;
  }
}

export function isGeoblockedFromVercel(src: string): boolean {
  try {
    const host = new URL(src).hostname.toLowerCase();
    return GEOBLOCKED_FROM_VERCEL.some(
      (d) => host === d || host.endsWith("." + d),
    );
  } catch {
    return false;
  }
}

export function resolveUrl(src: string): string {
  if (src.startsWith("/images/")) return `${API_BASE}${src}`;
  return src;
}

// True when the URL is unusable up-front (no need to attempt rendering).
export function isUnusableUrl(src: string | null | undefined): boolean {
  if (!src) return true;
  return isLikelyIcon(src) || isBrokenIranInternationalUrl(src);
}
