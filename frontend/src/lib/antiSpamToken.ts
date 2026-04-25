// Per-browser anti-spam token. Lives in localStorage, sent only on
// /api/v1/improvements POSTs via the X-DN-Anti-Spam header. Lets the
// backend dedupe anonymous «نامرتبط» votes without a tracking cookie:
//   - Not auto-sent by the browser (we attach it manually).
//   - User-clearable via DevTools / Clear Site Data.
//   - Never used outside the feedback flow.
// Privacy: footnote claim "بدون کوکی ردیابی، بدون تحلیل رفتار" still
// holds because (a) it's not a cookie, (b) it doesn't track behavior,
// (c) it isn't sent on page loads or third-party requests.

const STORAGE_KEY = "dn_anti_spam_token";

export function getAntiSpamToken(): string {
  if (typeof window === "undefined") return "";
  try {
    let token = window.localStorage.getItem(STORAGE_KEY);
    if (!token) {
      token = generateToken();
      window.localStorage.setItem(STORAGE_KEY, token);
    }
    return token;
  } catch {
    // Privacy-mode browsers throw on localStorage; fall back to a
    // per-page-load random token. Less effective for dedupe but still
    // harder to game than IP+UA alone.
    return generateToken();
  }
}

function generateToken(): string {
  const c: Crypto | undefined =
    typeof crypto !== "undefined" ? (crypto as Crypto) : undefined;
  if (c && typeof c.randomUUID === "function") {
    return c.randomUUID();
  }
  // Older browsers — assemble a UUID-shaped random string.
  const arr = new Uint8Array(16);
  if (c && typeof c.getRandomValues === "function") {
    c.getRandomValues(arr);
  } else {
    for (let i = 0; i < 16; i++) arr[i] = Math.floor(Math.random() * 256);
  }
  return Array.from(arr, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function antiSpamHeaders(): Record<string, string> {
  const token = getAntiSpamToken();
  return token ? { "X-DN-Anti-Spam": token } : {};
}
