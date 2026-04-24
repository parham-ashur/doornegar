// The top-level /dashboard/layout.tsx already renders DashboardNav for
// every dashboard page, so the HITL area doesn't need a second Farsi
// nav on top. Keep the layout as a pass-through so existing route
// structure stays intact, and subpages just render inside the shared
// max-w-6xl container from the parent layout.
export default function HitlLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
