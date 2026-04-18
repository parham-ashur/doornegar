"use client";

// Shared admin-token helper for HITL pages. Token lives in
// localStorage under the same key the main dashboard uses.
export function adminHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const t = localStorage.getItem("doornegar_admin_token") || "";
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export function hasAdminToken(): boolean {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem("doornegar_admin_token");
}
