"use client";

import { useEffect, useState } from "react";

interface Props {
  words: string[];
  // Match the existing «...» quote wrapping in تقابل روایت‌ها cards so the
  // visual is identical to the static version when there's only one word.
  quoted?: boolean;
}

// Picks one word from the list per page load. Server renders index 0 to
// keep hydration deterministic; on mount the client swaps in a random
// index, so each refresh / new visit lands on a different word without
// any in-place animation. Static after that.
export default function RotatingWord({ words, quoted = true }: Props) {
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    if (words.length > 1) {
      setIdx(Math.floor(Math.random() * words.length));
    }
  }, [words]);

  if (words.length === 0) return null;
  const word = words[idx] || "";
  return <>{quoted ? `«${word}»` : word}</>;
}
