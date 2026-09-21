const TONE: Record<string, string> = {
  active: "var(--success)",
  indexing: "var(--warning)",
  backfilling: "var(--warning)",
  onboarding: "var(--muted-foreground)",
  paused: "var(--muted-foreground)",
  error: "var(--destructive)",
  dead: "var(--destructive)",
  archived: "var(--muted-foreground)",
  pending_code: "var(--warning)",
  pending_password: "var(--warning)",
  disabled: "var(--muted-foreground)",
  flood_wait: "var(--warning)",
  running: "var(--warning)",
  succeeded: "var(--success)",
  failed: "var(--destructive)",
  queued: "var(--muted-foreground)",
};

/** A coloured dot carries status faster than a word, and the word stays next to it for clarity. */
export function StatusDot({ status, pulse }: { status: string; pulse?: boolean }) {
  const tone = TONE[status] ?? "var(--muted-foreground)";
  const busy = pulse ?? ["running", "indexing", "backfilling", "pending_code", "pending_password"].includes(status);
  return (
    <span className="relative grid h-2.5 w-2.5 shrink-0 place-items-center" title={status}>
      {busy ? (
        <span className="absolute h-2.5 w-2.5 animate-ping rounded-full opacity-60" style={{ background: tone }} />
      ) : null}
      <span className="relative h-2 w-2 rounded-full" style={{ background: tone }} />
    </span>
  );
}
