import type {
  TelegramAnalysis,
  TelegramClaim,
  TelegramPrediction,
} from "./types";

// Shared normalizers for Telegram-analysis predictions and claims.
//
// Predictions: the UI already labels the section "پیش‌بینی" ("prediction"),
// so leading "در آینده،" / "در آینده " the LLM sometimes emits is noise —
// strip it. Also strip "احتمالاً" when it follows "در آینده" since what
// remains would start awkwardly.
//
// Claims: the Pass-2 prompt asks the LLM to prefix each claim with
// "موضوع: <topic> | " to group competing claims about the same subject.
// That structure is useful internally but visually buries the actual
// claim. Strip any leading "<short label>: <value> | " — catches
// "موضوع:", "تعداد تلفات:", "عدد اعلام‌شده:" and similar.

export function cleanPrediction(text: string): string {
  if (!text) return "";
  let t = text.trim();
  // "در آینده،" / "در آینده ،" / "در آینده " — redundant prefix
  t = t.replace(/^در\s*آینده[،,]?\s*/, "");
  // Hedges at sentence-start — every prediction is probabilistic by
  // definition, so «احتمالاً» / «به احتمال زیاد» / «شاید» / «ممکن است»
  // in the lead position add length without information. Keep them
  // only when they're mid-sentence (where they attach to a clause)
  // or followed by a number («۷۰٪ احتمال دارد» stays).
  t = t.replace(/^(احتمالاً|احتمالا|به احتمال زیاد|شاید|ممکن است)(?=\s)/, "");
  // If stripping a hedge left a leading connector, drop it too.
  t = t.replace(/^[،,]\s*/, "");
  t = t.replace(/^که\s+/, "");
  return t.trim();
}

export function cleanClaim(text: string): string {
  if (!text) return "";
  let t = text.trim();
  // "موضوع: X | rest" → "rest" — short Persian label + "|" separator
  // from Pass-2's categorizer prefix.
  t = t.replace(/^[\u0600-\u06FF\s]{1,25}:\s*[^|]+\|\s*/, "");
  // "ادعا: «inner»" / "ادعا: inner" → "inner". Pass-2 sometimes wraps the
  // whole claim in this scaffold; the section header «ادعاهای کلیدی» already
  // tells the reader what they're looking at.
  t = t.replace(/^ادعا\s*:\s*/, "");
  // Credibility-label prefix that Niloofar polish writes («تأیید شده:»,
  // «مشکوک:», «تبلیغاتی:», «تک‌منبع:», «نیازمند تأیید:») — getCredLabel
  // pulls the label off the raw text, so we strip it here to avoid showing
  // it twice (once in the bullet, once as the colored label below).
  t = t.replace(/^(?:تأیید شده|تایید شده|مشکوک|تبلیغاتی|تک[‌\s]?منبع|نیازمند تأیید|نیازمند تایید|تأیید نشده|تایید نشده)\s*:\s*/, "");
  t = t.replace(/^[«"]([^»"]+)[»"]\s*/, "$1");
  // Trailing « — کانال X [descriptor]» or « — ارزیابی: ...» tails. These
  // attribute the claim or grade its credibility — the credibility goes to
  // the label below the card; the channel name is gone by policy.
  t = t.replace(/\s*[—–-]\s*کانال\s+[^—–\-]+(?=\s*[—–\-]|\s*$)/g, "");
  t = t.replace(/\s*[—–-]\s*(?:کانال‌های|رسانه‌های)\s+[^—–\-]+(?=\s*[—–\-]|\s*$)/g, "");
  t = t.replace(/\s*[—–-]\s*ارزیابی\s*:\s*.+$/, "");
  // Verbose attribution verbs that Parham flagged as non-essential:
  //   «کانال [X] اعلام کرد/کرده است/کرده‌اند/ادعا کردند که …»
  //   «کانال‌های حکومتی نزدیک به دولت ادعا کردند …»
  //   «به گفتهٔ کانال X، …»
  //   «رسانه‌های تلگرامی نوشتند …»
  // We don't cover every possible phrasing — the Niloofar polish step
  // handles the long tail. This strips the most common offenders for
  // un-polished fallback text.
  //
  // Earlier regexes missed plural «کردند» and perfect «کرده است», leaving
  // orphan «ند» or «کرده است که» at the start of a claim. The verb
  // alternation below is split into (a) compound verbs that require a
  // «کرد(ند/ه است/ه‌اند)» tail and (b) standalone verbs (گفت/نوشت) that
  // take inflection suffixes directly.
  // NB: alternation is tried left-to-right, so longer endings MUST come
  // before their prefixes — otherwise «کرد» matches before «کردند» and
  // leaves the «ند» orphan at the start of the claim.
  const COMPOUND = "(?:اعلام|ادعا|اظهار|گزارش|تأکید|تاکید)\\s*(?:کرده است|کرده‌اند|کرده اند|کردند|کرد)";
  const STANDALONE = "(?:گفت|نوشت)(?:ه است|ه‌اند|ه اند|ند)?";
  const EZAFE = "(?:اظهار\\s+(?:داشته است|داشتند|داشت))";
  const ATTR = `(?:${COMPOUND}|${STANDALONE}|${EZAFE})`;

  // «کانال X [descriptor] <verb>» and «کانال‌های/رسانه‌های X <verb>»
  t = t.replace(
    new RegExp(`^کانال(?:‌های)?\\s+[^،]{1,60}\\s+${ATTR}\\s*(که\\s+)?`),
    "",
  );
  t = t.replace(
    new RegExp(`^(کانال‌های|رسانه‌های)\\s+[^،]{1,60}\\s+${ATTR}\\s*(که\\s+)?`),
    "",
  );
  t = t.replace(/^به گفتهٔ\s+[^،]+،\s*/, "");
  return t.trim();
}

export function displayPredictions(a: TelegramAnalysis | null | undefined): TelegramPrediction[] {
  return a?.predictions_display || a?.predictions || [];
}

export function displayClaims(a: TelegramAnalysis | null | undefined): TelegramClaim[] {
  return a?.key_claims_display || a?.key_claims || [];
}

export interface CredLabel {
  label: string;
  color: string;
}

// Niloofar's polish step prefixes each claim with one of these exact
// labels followed by a colon. Free-text fallbacks below cover pre-polish
// claims that still carry an "(… — cred)" suffix from pass-2.
export function getCredLabel(t: string): CredLabel | null {
  if (/^تأیید شده\s*:|^تایید شده\s*:/.test(t)) return { label: "تأیید شده", color: "text-emerald-500" };
  if (/^مشکوک\s*:/.test(t)) return { label: "مشکوک", color: "text-red-500" };
  if (/^تبلیغاتی\s*:/.test(t)) return { label: "تبلیغاتی", color: "text-red-400" };
  if (/^تک[‌\s]?منبع\s*:/.test(t)) return { label: "تک‌منبع", color: "text-amber-500" };
  if (/^نیازمند تأیید\s*:|^نیازمند تایید\s*:/.test(t)) return { label: "نیازمند تأیید", color: "text-amber-500" };
  if (/مشکوک|اغراق|بعید|غیرواقعی/.test(t)) return { label: "مشکوک", color: "text-red-500" };
  if (/تبلیغاتی|جنبه تبلیغی|پروپاگاند/.test(t)) return { label: "تبلیغاتی", color: "text-red-400" };
  if (/نیازمند.*تایید|نیازمند.*تأیید|نیاز به تایید|نیاز به تأیید|تأیید نشده|تایید نشده|قابل.تأیید نیست|نیازمند.*مستقل|صحت.*نیاز/.test(t)) return { label: "تأیید نشده", color: "text-amber-500" };
  if (/قابل.اعتبار|تایید شده|تأیید شده|قابل.اعتماد|قابل.استناد|معتبر|موثق/.test(t)) return { label: "تأیید شده", color: "text-emerald-500" };
  return null;
}

// Aggressive plain-text cleaner for raw Telegram post bodies (the
// `text` field on /social/stories/{id}/social posts). Strips the same
// decorative noise the backend's `clean_post_for_display` removes —
// kept on the client too so legacy posts that pre-date the backend
// cleaner still render uniformly.
// Decorative emoji leads at line start. Matched without the /u flag (target=es5)
// so we spell out astral chars as surrogate pairs:
//   🔻U+1F53B \uD83D\uDD3B   🔺U+1F53A \uD83D\uDD3A   🔸U+1F538 \uD83D\uDD38
//   🔹U+1F539 \uD83D\uDD39   📢U+1F4E2 \uD83D\uDCE2   📻U+1F4FB \uD83D\uDCFB
//   🎥U+1F3A5 \uD83C\uDFA5   🔥U+1F525 \uD83D\uDD25   📌U+1F4CC \uD83D\uDCCC
//   🔗U+1F517 \uD83D\uDD17   🕑U+1F551 \uD83D\uDD51   ▶ U+25B6   ⚠ U+26A0   ⭐ U+2B50
const TG_DECORATIVE_LEADS_RE = /^[\s\u202B\u202C]*(?:\uD83D[\uDD3A\uDD3B\uDD38\uDD39\uDCE2\uDCFB\uDD25\uDCCC\uDD17\uDD51]|\uD83C\uDFA5|[\u25B6\u26A0\u2B50])+[\s\u202B\u202C]*/gm;

export function cleanPostBody(text: string | null | undefined): string {
  if (!text) return "";
  let out = text;
  // Markdown links → label only
  out = out.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  // Bare URLs
  out = out.replace(/https?:\/\/\S+/g, "");
  // @mentions
  out = out.replace(/@\w+/g, "");
  // **bold** wrappers (keep inner)
  out = out.replace(/\*\*([^*]+)\*\*/g, "$1");
  // Leading decorative emoji per line
  out = out.replace(TG_DECORATIVE_LEADS_RE, "");
  // Leading bullet markers per line
  out = out.replace(/^[\s\u202B\u202C]*[•·▪◾◼·]\s*/gm, "");
  // Trailing channel attribution like "│ کانال X" or "@channel"
  out = out.replace(/[│|]\s*(کانال|@)\s*[^\n│|]+\s*$/gm, "");
  // Collapse whitespace
  out = out.replace(/[ \t]+/g, " ");
  out = out.replace(/\n{3,}/g, "\n\n");
  return out.trim();
}

// Accepts either a string or the object shape { text, pct, supporters }.
export function predictionText(p: unknown): string {
  if (!p) return "";
  if (typeof p === "string") return cleanPrediction(p);
  if (typeof p === "object" && "text" in (p as Record<string, unknown>)) {
    return cleanPrediction(String((p as { text?: unknown }).text ?? ""));
  }
  return "";
}

export function claimText(c: unknown): string {
  if (!c) return "";
  if (typeof c === "string") return cleanClaim(c);
  if (typeof c === "object" && "text" in (c as Record<string, unknown>)) {
    return cleanClaim(String((c as { text?: unknown }).text ?? ""));
  }
  return "";
}
