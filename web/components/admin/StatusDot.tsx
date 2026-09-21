/**
 * How every state in the studio and the console is written: a dot for speed, the
 * word beside it for certainty. Colour on its own is not a label.
 */

type Tone = "good" | "busy" | "bad" | "idle";

const TONES: Record<string, Tone> = {
  // channels
  active: "good",
  indexing: "busy",
  backfilling: "busy",
  onboarding: "idle",
  paused: "idle",
  archived: "idle",
  error: "bad",
  // telegram accounts
  pending_code: "busy",
  pending_password: "busy",
  flood_wait: "busy",
  disabled: "idle",
  dead: "bad",
  // jobs
  queued: "idle",
  running: "busy",
  succeeded: "good",
  failed: "bad",
  // drafts
  draft: "idle",
  scheduled: "busy",
  publishing: "busy",
  published: "good",
  canceled: "idle",
};

/** Plain words for states whose internal name would puzzle the reader. */
const WORDS: Record<string, string> = {
  pending_code: "waiting for the code",
  pending_password: "waiting for the password",
  flood_wait: "rate limited",
  dead: "signed out",
  backfilling: "importing history",
  indexing: "indexing",
  onboarding: "not set up yet",
  draft: "not sent",
  scheduled: "scheduled",
  publishing: "sending",
  published: "sent",
  canceled: "cancelled",
  failed: "failed",
  succeeded: "done",
  running: "running",
  queued: "waiting",
};

export function toneOf(status: string): Tone {
  return TONES[status] ?? "idle";
}

export function stateWord(status: string): string {
  return WORDS[status] ?? status.replace(/_/g, " ");
}

/** Dot and word together. */
export function State({ status, label }: { status: string; label?: string }) {
  const tone = toneOf(status);
  return (
    <span className="state" data-tone={tone} data-busy={tone === "busy"}>
      {label ?? stateWord(status)}
    </span>
  );
}

/** The dot alone, for rows that already name the state in their own words. */
export function StatusDot({ status, pulse }: { status: string; pulse?: boolean }) {
  const tone = toneOf(status);
  return (
    <span
      className="state shrink-0"
      data-tone={tone}
      data-busy={pulse ?? tone === "busy"}
      title={stateWord(status)}
    />
  );
}
