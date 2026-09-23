"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { SparkIcon } from "@/components/Icons";
import { State } from "@/components/admin/StatusDot";
import { post } from "@/lib/client";
import { fullDate } from "@/lib/format";
import type { DraftOut } from "@/lib/types";

export function DraftList({ initial }: { initial: DraftOut[] }) {
  const t = useTranslations("studio.drafts");
  const status = useTranslations("studio.status");
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
            placeholder={t("brief")}
            className="input-field"
          />
          <button
            onClick={() => void create(true)}
            disabled={busy || brief.trim().length < 3}
            className="btn-primary shrink-0"
          >
            <SparkIcon size={14} />
            {t("write")}
          </button>
        </div>
        <button
          onClick={() => void create(false)}
          disabled={busy}
          className="mt-2 text-xs text-muted-foreground hover:text-foreground"
        >
          {t("orEmpty")}
        </button>
        {error ? (
          <p className="mt-2 text-sm" style={{ color: "var(--destructive)" }}>
            {error}
          </p>
        ) : null}
      </div>

      {initial.length === 0 ? (
        <p className="border-t py-16 text-center text-sm text-muted-foreground">
          {t("empty")}
        </p>
      ) : (
        <ul className="rows mt-8 border-t">
          {initial.map((d) => (
            <li key={d.id} className="row">
              <div className="row-margin">
                <State status={d.status} label={status.has(d.status) ? status(d.status) : undefined} />
                {d.scheduled_at ? (
                  <span suppressHydrationWarning>{fullDate(d.scheduled_at, locale)}</span>
                ) : null}
              </div>
              <div className="row-body">
                <Link href={`/studio/drafts/${d.id}`} className="block hover:text-primary">
                  <span className="block truncate text-[0.9375rem] font-medium">
                    {d.title || stripTags(d.html) || t("untitled")}
                  </span>
                </Link>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {d.publish_error ? (
                    <span style={{ color: "var(--destructive)" }}>{d.publish_error}</span>
                  ) : (
                    <>
                      {t("characters", { count: d.length })}
                      {d.ai_generated ? t("byAssistant") : ""}
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
