import type { ReactNode } from "react";

interface StoryContentSectionProps {
  title: string;
  children: ReactNode;
}

export function StoryContentSection({ title, children }: StoryContentSectionProps) {
  return (
    <section className="border-b border-slate-200 px-6 py-8 dark:border-slate-800">
      <h3 className="text-[12px] font-bold uppercase tracking-wider text-slate-400">{title}</h3>
      <div className="mt-3 text-[14px] leading-7 text-slate-700 dark:text-slate-300">{children}</div>
    </section>
  );
}

interface StoryContentPanelProps {
  children: ReactNode;
}

export default function StoryContentPanel({ children }: StoryContentPanelProps) {
  return <div className="pb-24">{children}</div>;
}
