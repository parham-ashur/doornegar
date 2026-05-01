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
    <>
      {/* Operator opt-out: visit any page with ?umami=off to disable
          tracking on this browser, ?umami=on to re-enable. Reads the
          flag Umami's own tracker checks on every event. Runs before
          the tracker so a fresh ?umami=off visit isn't counted. */}
      <Script id="umami-opt-out" strategy="beforeInteractive">{`
(function(){try{
  var p=new URLSearchParams(window.location.search);
  var v=p.get('umami');
  if(v==='off'){localStorage.setItem('umami.disabled','1');}
  else if(v==='on'){localStorage.removeItem('umami.disabled');}
  else{return;}
  p.delete('umami');
  var q=p.toString();
  history.replaceState(null,'',window.location.pathname+(q?'?'+q:'')+window.location.hash);
}catch(e){}})();
      `}</Script>
      <Script
        src={src}
        data-website-id={websiteId}
        strategy="afterInteractive"
        // Tell Umami to respect Do-Not-Track, not that there's anything
        // privacy-sensitive being sent anyway.
        data-do-not-track="true"
      />
    </>
  );
}
