const TONE_CLASS: Record<string, string> = {
  good: "pill pill--good",
  warning: "pill pill--warning",
  serious: "pill pill--serious",
  critical: "pill pill--critical",
  neutral: "pill pill--neutral",
};

export function StatusPill({ tone, children }: { tone: keyof typeof TONE_CLASS; children: React.ReactNode }) {
  return <span className={TONE_CLASS[tone]}>{children}</span>;
}
