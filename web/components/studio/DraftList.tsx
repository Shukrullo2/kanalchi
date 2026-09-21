"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale } from "next-intl";
import { useState } from "react";
import { SparkIcon } from "@/components/Icons";
import { State } from "@/components/admin/StatusDot";
import { post } from "@/lib/client";
import { fullDate } from "@/lib/format";
import type { DraftOut } from "@/lib/types";

export function DraftList({ initial }: { initial: DraftOut[] }) {
  const router = useRouter();
  const locale = useLocale();
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
    <div>
      <div className="max-w-xl">
        <div className="flex gap-2">
          <input
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            placeholder="What should this post be about?"
            className="input-field"
          />
          <button
            onClick={() => void create(true)}
            disabled={busy || brief.trim().length < 3}
            className="btn-primary shrink-0"
          >
            <SparkIcon size={14} />
            Write a draft
          </button>
        </div>
        <button
          onClick={() => void create(false)}
          disabled={busy}
          className="mt-2 text-xs text-muted-foreground hover:text-foreground"
        >
          Or start from an empty post
        </button>
        {error ? (
          <p className="mt-2 text-sm" style={{ color: "var(--destructive)" }}>
            {error}
          </p>
        ) : null}
      </div>

      {initial.length === 0 ? (
        <p className="border-t py-16 text-center text-sm text-muted-foreground">
          Nothing written yet. Describe a post above and the assistant will start one.
        </p>
      ) : (
        <ul className="rows mt-8 border-t">
          {initial.map((d) => (
            <li key={d.id} className="row">
              <div className="row-margin">
                <State status={d.status} />
                {d.scheduled_at ? (
                  <span suppressHydrationWarning>{fullDate(d.scheduled_at, locale)}</span>
                ) : null}
              </div>
              <div className="row-body">
                <Link href={`/studio/drafts/${d.id}`} className="block hover:text-primary">
                  <span className="block truncate text-[0.9375rem] font-medium">
                    {d.title || stripTags(d.html) || "Untitled draft"}
                  </span>
                </Link>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {d.publish_error ? (
                    <span style={{ color: "var(--destructive)" }}>{d.publish_error}</span>
                  ) : (
                    <>
                      {d.length} characters
                      {d.ai_generated ? ", drafted by the assistant" : ""}
                    </>
                  )}
                </p>
              </div>
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
