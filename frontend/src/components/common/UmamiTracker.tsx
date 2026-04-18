import Script from "next/script";

/**
 * Umami analytics tracker — privacy-first, self-hosted.
 *
 * Loads only when BOTH env vars are set, so dev/previews stay clean
 * and accidental missing config fails closed (no tracking) rather
 * than open (leaking events to a stale endpoint).
 *
 * - NEXT_PUBLIC_UMAMI_SRC: full URL to umami's script.js, e.g.
 *     https://analytics.doornegar.org/script.js
 *     (or https://<railway-app>.up.railway.app/script.js before
 *     the custom subdomain is wired)
 * - NEXT_PUBLIC_UMAMI_WEBSITE_ID: UUID of the website row inside
 *     the Umami admin panel
 *
 * Umami by design does not store IPs, set cookies, or fingerprint
 * devices — the script is ~2KB and sends one beacon per pageview
 * with only the page path, referrer, language, and screen size.
 * That matches Doornegar's threat model for Iranian readers.
 */
export default function UmamiTracker() {
  const src = process.env.NEXT_PUBLIC_UMAMI_SRC;
  const websiteId = process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID;

  if (!src || !websiteId) return null;

  return (
    <Script
      src={src}
      data-website-id={websiteId}
      strategy="afterInteractive"
      // Tell Umami to respect Do-Not-Track, not that there's anything
      // privacy-sensitive being sent anyway.
      data-do-not-track="true"
    />
  );
}
