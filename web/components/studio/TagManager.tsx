"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { call, patch, post } from "@/lib/client";
import { tagLabel } from "@/lib/labels";
import type { PendingTag, TagOut } from "@/lib/types";
import { toneVar } from "@/lib/dimensions";

export function TagManager({
  pending,
  tags,
  locale,
}: {
  pending: PendingTag[];
  tags: TagOut[];
  locale: string;
}) {
  const router = useRouter();
  const [queue, setQueue] = useState(pending);
  const [mergeFrom, setMergeFrom] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setNotice(label);
      setQueue(await call<PendingTag[]>("/api/studio/tags/pending"));
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      {error ? (
        <p className="text-sm" style={{ color: "var(--destructive)" }}>
          {error}
        </p>
      ) : null}
      {notice ? <p className="text-sm text-muted-foreground">{notice}</p> : null}

      <section className="card-surface overflow-hidden">
        <header className="flex items-center justify-between gap-3 border-b px-4 py-3">
          <h2 className="text-sm font-medium">Waiting for review</h2>
          <button
            onClick={() => void run("Taxonomy rebuild queued.", () => post("/api/studio/taxonomy/rebuild", {}))}
            disabled={busy}
            className="btn-ghost py-1 text-xs"
          >
            Rebuild taxonomy
          </button>
        </header>
        {queue.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">
            Nothing waiting. New names are added automatically once they recur.
          </p>
        ) : (
          <ul className="divide-y">
            {queue.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ background: toneVar(c.dimension) }}
                  aria-hidden
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{c.name}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {c.dimension} · seen {c.count}×
                    {c.surface_forms.length > 1 ? ` · ${c.surface_forms.slice(0, 3).join(", ")}` : ""}
                  </span>
                </span>
                <button
                  onClick={() => void run(`Added “${c.name}”.`, () => post(`/api/studio/tags/pending/${c.id}/promote`, {}))}
                  disabled={busy}
                  className="btn-primary py-1 text-xs"
                >
                  Add as tag
                </button>
                <button
                  onClick={() => void run("Dismissed.", () => post(`/api/studio/tags/pending/${c.id}/reject`, {}))}
                  disabled={busy}
                  className="link-quiet text-xs"
                >
                  ignore
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card-surface overflow-hidden">
        <header className="border-b px-4 py-3">
          <h2 className="text-sm font-medium">Your tags</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Hiding or merging a tag is remembered, so a later rebuild will not undo it.
          </p>
        </header>
        <ul className="divide-y">
          {tags.map((t) => (
            <li key={t.slug} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
              <span
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ background: toneVar(t.dimension) }}
                aria-hidden
              />
              <span className="min-w-0 flex-1 truncate text-sm">{tagLabel(t, locale)}</span>
              <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{t.post_count}</span>
              {mergeFrom === t.slug ? (
                <select
                  autoFocus
                  className="input-field w-auto py-1 text-xs"
                  onChange={(e) => {
                    const into = e.target.value;
                    if (into) void run(`Merged into ${into}.`, () => post(`/api/studio/tags/${t.slug}/merge`, { into }));
                    setMergeFrom(null);
                  }}
                  defaultValue=""
                >
                  <option value="">merge into…</option>
                  {tags
                    .filter((o) => o.slug !== t.slug && o.dimension === t.dimension)
                    .map((o) => (
                      <option key={o.slug} value={o.slug}>
                        {tagLabel(o, locale)}
                      </option>
                    ))}
                </select>
              ) : (
                <button onClick={() => setMergeFrom(t.slug)} className="link-quiet text-xs">
                  merge
                </button>
              )}
              <button
                onClick={() => void run(`Hid “${t.name}”.`, () => patch(`/api/studio/tags/${t.slug}`, { hidden: true }))}
                disabled={busy}
                className="link-quiet text-xs"
              >
                hide
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
