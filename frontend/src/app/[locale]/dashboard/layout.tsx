import DashboardNav from "@/components/dashboard/DashboardNav";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div dir="ltr" className="min-h-screen bg-white dark:bg-slate-950">
      <DashboardNav />
      <div className="max-w-6xl mx-auto px-4 py-6">{children}</div>
    </div>
  );
}
