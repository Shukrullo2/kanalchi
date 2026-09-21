"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { SparkIcon } from "@/components/Icons";
import { StatusDot } from "@/components/admin/StatusDot";
import { post } from "@/lib/client";
import type { DraftOut } from "@/lib/types";

const TONE: Record<string, string> = {
  draft: "queued",
  scheduled: "running",
  publishing: "running",
  published: "succeeded",
  failed: "failed",
  canceled: "queued",
};

export function DraftList({ initial }: { initial: DraftOut[] }) {
  const router = useRouter();
  const [brief, setBrief] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create(withAI: boolean) {
    setBusy(true);
    setError(null);
    try {
      const draft = withAI
        ? await post<DraftOut>("/api/studio/drafts/ai", { brief })
        : await post<DraftOut>("/api/studio/drafts", { html: "", title: "" });
      router.push(`/studio/drafts/${draft.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="card-surface space-y-2.5 p-4">
        <div className="flex gap-2">
          <input
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            placeholder="What should the post be about?"
            className="input-field"
          />
          <button
            onClick={() => void create(true)}
            disabled={busy || brief.trim().length < 3}
            className="btn-primary shrink-0"
          >
            <SparkIcon size={14} />
            Draft it
          </button>
        </div>
        <button onClick={() => void create(false)} disabled={busy} className="text-xs text-muted-foreground hover:text-foreground">
          or start from a blank post
        </button>
        {error ? (
          <p className="text-sm" style={{ color: "var(--destructive)" }}>
            {error}
          </p>
        ) : null}
      </div>

      {initial.length === 0 ? (
        <div className="card-surface p-12 text-center text-sm text-muted-foreground">No drafts yet.</div>
      ) : (
        <ul className="card-surface divide-y overflow-hidden">
          {initial.map((d) => (
            <li key={d.id}>
              <Link href={`/studio/drafts/${d.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-surface-2">
                <StatusDot status={TONE[d.status] ?? "queued"} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    {d.title || stripTags(d.html) || "Untitled"}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {d.status}
                    {d.scheduled_at ? ` · ${new Date(d.scheduled_at).toLocaleString()}` : ""}
                    {d.publish_error ? ` · ${d.publish_error}` : ""}
                  </span>
                </span>
                {d.ai_generated ? <span className="chip">AI</span> : null}
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{d.length}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 80);
}
