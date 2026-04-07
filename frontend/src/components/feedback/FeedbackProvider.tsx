"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

interface FeedbackContextValue {
  isRater: boolean;
  token: string | null;
}

const FeedbackContext = createContext<FeedbackContextValue>({
  isRater: false,
  token: null,
});

export function useFeedback() {
  return useContext(FeedbackContext);
}

export default function FeedbackProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem("doornegar_token");
    if (saved) setToken(saved);
  }, []);

  return (
    <FeedbackContext.Provider value={{ isRater: !!token, token }}>
      {children}
    </FeedbackContext.Provider>
  );
}
