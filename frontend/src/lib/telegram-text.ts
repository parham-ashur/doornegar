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
  // Capitalize-like cleanup: if the next word is a connector that leaves
  // an awkward start ("، " / "و ")
  t = t.replace(/^[،,]\s*/, "");
  return t.trim();
}

export function cleanClaim(text: string): string {
  if (!text) return "";
  let t = text.trim();
  // "موضوع: X | رست claim" → "rest claim"
  // Label is any short (1–25 char) Persian word ending in a colon, followed
  // by the topic, a pipe, then the claim body.
  t = t.replace(/^[\u0600-\u06FF\s]{1,25}:\s*[^|]+\|\s*/, "");
  return t.trim();
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
