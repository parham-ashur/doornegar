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
  // Verbose attribution verbs that Parham flagged as non-essential:
  //   «کانال [X] اعلام کرد/کرده است که …»
  //   «کانال‌های حکومتی اعلام کردند …»
  //   «به گفتهٔ کانال X، …»
  //   «رسانه‌های تلگرامی نوشتند …»
  // We don't cover every possible phrasing — the Niloofar polish step
  // handles the long tail. This strips the most common offenders for
  // un-polished fallback text.
  t = t.replace(
    /^کانال(?:‌های)?\s+[^\s،]{1,40}(?:\s+[^\s،]{1,40})?\s+(اعلام|گفت|نوشت|اظهار داشت|اظهار کرد)(?:ند)?(?:ه? است)?\s*(که\s+)?/,
    "",
  );
  t = t.replace(
    /^(کانال‌های|رسانه‌های)\s+[^\s،]{1,40}\s+(اعلام|گفتند|نوشتند|اظهار کردند)(?:ند)?\s*(که\s+)?/,
    "",
  );
  t = t.replace(/^به گفتهٔ\s+[^،]+،\s*/, "");
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
