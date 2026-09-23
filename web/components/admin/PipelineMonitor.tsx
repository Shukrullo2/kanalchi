"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { StatusDot } from "@/components/admin/StatusDot";
import { call, post } from "@/lib/client";
import type { Checklist, PipelineEstimate, PipelineStage, PipelineStatus } from "@/lib/types";

const STAGES: { key: Exclude<PipelineStage, "done">; label: string }[] = [
  { key: "import", label: "Import history" },
  { key: "profile", label: "Profile the channel" },
  { key: "embed", label: "Embeddings" },
  { key: "extract", label: "Extraction" },
  { key: "taxonomy", label: "Index" },
];

const LINES: Record<string, string> = {
  extraction: "extraction",
  embedding: "embeddings",
  profile: "channel profile",
  taxonomy: "index build",
  summaries: "summaries",
};

/**
 * Where an import stands, refreshed every few seconds from the database rather than from
 * whichever job last reported. It keeps polling through a dead API (with a widening gap
 * and a plain "reconnecting" line) so a tab left open never shows a stale picture as if
 * it were live, and its one button re-queues whatever step is missing.
 */
export function PipelineMonitor({
  tenantId,
  initial,
  showEstimate = true,
}: {
  tenantId: number;
  initial?: Checklist | null;
  showEstimate?: boolean;
}) {
  const [checklist, setChecklist] = useState<Checklist | null>(initial ?? null);
  const [estimate, setEstimate] = useState<PipelineEstimate | null>(null);
  const [offline, setOffline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const failures = useRef(0);
  const stageRef = useRef<PipelineStage | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await call<Checklist>(`/api/admin/tenants/${tenantId}/checklist`);
      setChecklist(next);
      stageRef.current = next.pipeline?.stage ?? null;
      failures.current = 0;
      setOffline(false);
    } catch {
      failures.current += 1;
      setOffline(true);
    }
  }, [tenantId]);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      await refresh();
      if (stopped) return;
      const idle = stageRef.current === "done";
      const delay = Math.min(30_000, (idle ? 15_000 : 4_000) * (failures.current + 1));
      timer = setTimeout(tick, delay);
    };
    timer = setTimeout(tick, initial ? 4_000 : 0);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
    // `initial` only decides whether the first read can wait.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh]);

  const stage = checklist?.pipeline?.stage;
  useEffect(() => {
    if (!showEstimate) return;
    let live = true;
    call<PipelineEstimate>(`/api/admin/tenants/${tenantId}/estimate`)
      .then((e) => live && setEstimate(e))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [tenantId, stage, showEstimate]);

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    setNote(null);
    try {
      const out = (await fn()) as { actions?: string[] } | undefined;
      setNote(out?.actions ? out.actions.join(" · ") : `${label}: ok`);
      await refresh();
    } catch (e) {
      setNote(`${label}: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  const p = checklist?.pipeline;
  if (!p) {
    return <p className="text-sm text-muted-foreground">{offline ? "Reconnecting…" : "Loading…"}</p>;
  }
  const s = p.stages;
  const importStarted = s.import.status !== null && s.import.status !== undefined;
  const paused = p.tenant_status === "paused";

  return (
    <section className="card-surface p-4">
      <div className="flex flex-wrap items-center gap-3">
        <StatusDot status={p.stage === "done" ? "active" : paused ? "paused" : "indexing"} />
        <span className="text-sm font-medium">{headline(p)}</span>
        <span className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
          <Worker name="telegram" alive={p.workers.telegram} />
          <Worker name="index" alive={p.workers.index} />
          {offline ? <span style={{ color: "var(--warning)" }}>reconnecting…</span> : null}
        </span>
      </div>

      {showEstimate && estimate ? <Estimate estimate={estimate} finished={p.stage === "done"} /> : null}

      <ol className="mt-4 space-y-3">
        {STAGES.map(({ key, label }) => (
          <li key={key} className="grid gap-1 sm:grid-cols-[10rem_1fr] sm:items-center">
            <span className="flex items-center gap-2 text-sm">
              <span
                className="grid h-4 w-4 shrink-0 place-items-center rounded-full text-[0.6rem] font-semibold"
                style={
                  s[key].done
                    ? { background: "var(--success)", color: "var(--background)" }
                    : key === p.stage
                      ? { background: "var(--primary)", color: "var(--primary-foreground)" }
                      : { background: "var(--surface-2)", color: "var(--muted-foreground)" }
                }
                aria-hidden
              >
                {s[key].done ? "✓" : ""}
              </span>
              {label}
            </span>
            <StageLine stage={key} p={p} />
          </li>
        ))}
      </ol>

      {p.running.length > 0 ? (
        <ul className="mt-3 space-y-0.5 text-xs text-muted-foreground">
          {p.running.map((r, i) => (
            <li key={i}>
              running: {r.type}
              {typeof r.progress.stage === "string" ? ` · ${r.progress.stage}` : ""}
              {typeof r.progress.done === "number" ? ` · ${r.progress.done}${typeof r.progress.total === "number" ? ` / ${r.progress.total}` : ""}` : ""}
            </li>
          ))}
        </ul>
      ) : null}

      {p.attention.length > 0 ? (
        <ul className="mt-3 space-y-1 border-l-2 pl-3 text-sm" style={{ borderColor: "var(--warning)" }}>
          {p.attention.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
        {!importStarted || (s.import.status !== "done" && s.import.status !== "running") ? (
          <button
            disabled={busy || paused}
            onClick={() => void run("import", () => post(`/api/admin/tenants/${tenantId}/start`))}
            className="btn-primary"
          >
            {importStarted ? "Resume import" : "Start import"}
          </button>
        ) : null}
        <button
          disabled={busy || paused}
          onClick={() => void run("resume", () => post(`/api/admin/tenants/${tenantId}/pipeline/reconcile`))}
          className="btn-ghost"
          title="Queues whatever step is missing. Safe to press any number of times."
        >
          Resume pipeline
        </button>
        {note ? <span className="text-xs text-muted-foreground">{note}</span> : null}
      </div>
    </section>
  );
}

function headline(p: PipelineStatus): string {
  if (p.tenant_status === "paused") return "Paused";
  switch (p.stage) {
    case "import":
      return p.stages.import.status === "running" ? "Importing history" : "Waiting to import";
    case "profile":
      return "Profiling the channel";
    case "embed":
      return "Embedding posts";
    case "extract":
      return p.stages.extract.in_flight > 0 ? "Extraction batch in flight" : "Extracting";
    case "taxonomy":
      return p.stages.taxonomy.status === "proposed" ? "Index proposed, waiting to be applied" : "Building the index";
    default:
      return "Indexed";
  }
}

function Worker({ name, alive }: { name: string; alive: boolean | null }) {
  return (
    <span className="flex items-center gap-1">
      <StatusDot status={alive === null ? "onboarding" : alive ? "active" : "error"} pulse={false} />
      worker-{name}
    </span>
  );
}

function Bar({ value, total }: { value: number; total: number | null }) {
  const pct = total ? Math.min(100, Math.round((value / total) * 100)) : 0;
  return (
    <span className="block h-1.5 w-full overflow-hidden rounded-full bg-border">
      <span className="block h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
    </span>
  );
}

function StageLine({ stage, p }: { stage: Exclude<PipelineStage, "done">; p: PipelineStatus }) {
  const s = p.stages;
  const muted = "text-xs tabular-nums text-muted-foreground";
  switch (stage) {
    case "import":
      return (
        <span className="grid gap-1 sm:grid-cols-[1fr_12rem] sm:items-center">
          <Bar value={s.import.imported} total={s.import.total} />
          <span className={muted}>
            {s.import.imported} / {s.import.total ?? "?"} posts{s.import.status ? ` · ${s.import.status}` : " · not started"}
          </span>
        </span>
      );
    case "profile":
      return (
        <span className={muted}>
          {s.profile.done ? "done" : s.profile.possible ? "pending" : "needs a few posts first"}
        </span>
      );
    case "embed":
      return (
        <span className="grid gap-1 sm:grid-cols-[1fr_12rem] sm:items-center">
          <Bar value={s.embed.embedded + s.embed.skipped} total={s.embed.total} />
          <span className={muted}>
            {s.embed.embedded} / {s.embed.total} posts
            {s.embed.skipped ? ` · ${s.embed.skipped} too short` : ""}
          </span>
        </span>
      );
    case "extract":
      return (
        <span className="grid gap-1 sm:grid-cols-[1fr_12rem] sm:items-center">
          <Bar value={s.extract.succeeded} total={s.extract.total} />
          <span className={muted}>
            {s.extract.succeeded} / {s.extract.total} posts
            {s.extract.in_flight ? ` · ${s.extract.in_flight} in flight` : ""}
            {s.extract.failed ? ` · ${s.extract.failed} failed` : ""}
          </span>
        </span>
      );
    case "taxonomy":
      return (
        <span className={muted}>
          {s.taxonomy.version_no
            ? `version ${s.taxonomy.version_no} · ${s.taxonomy.status}${s.taxonomy.done ? " · live" : ""}`
            : "not built yet"}
        </span>
      );
  }
}

function Estimate({ estimate, finished }: { estimate: PipelineEstimate; finished: boolean }) {
  const lines = Object.entries(estimate.lines).filter(([, usd]) => usd > 0);
  return (
    <div className="mt-3 rounded-lg bg-surface-2 p-3 text-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-medium">
          {finished ? "Ongoing cost" : "Estimated cost to finish"}: about ${estimate.total_usd.toFixed(2)}
        </span>
        <span className="text-xs text-muted-foreground">
          {estimate.posts_total} posts ·{" "}
          {estimate.measured_from_channel
            ? `${estimate.avg_post_tokens} tokens a post, measured`
            : `assuming ${estimate.avg_post_tokens} tokens a post`}
        </span>
      </div>
      {lines.length > 0 ? (
        <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
          {lines.map(([k, usd]) => (
            <li key={k} className="tabular-nums">
              {LINES[k] ?? k} ${usd.toFixed(2)}
            </li>
          ))}
          {estimate.extraction_measured_usd !== undefined ? (
            <li className="tabular-nums">token-counted extraction ${estimate.extraction_measured_usd.toFixed(2)}</li>
          ) : null}
        </ul>
      ) : null}
      <p className="mt-1.5 text-xs text-muted-foreground">
        Extraction is priced from {estimate.models.extract} at batch rates; the rest from what the first channel
        cost. Actual spend lands in Costs as it happens.
      </p>
    </div>
  );
}
