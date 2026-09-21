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
    <div>
      {error ? (
        <p className="text-sm" style={{ color: "var(--destructive)" }}>
          {error}
        </p>
      ) : null}
      {notice ? <p className="text-sm text-muted-foreground">{notice}</p> : null}

      <section>
        <header className="flex items-center justify-between gap-3 border-b pb-2.5">
          <h2 className="text-[0.9375rem] font-medium">Names waiting to be filed</h2>
          <button
            onClick={() => void run("Rebuilding the index — it runs in the background.", () => post("/api/studio/taxonomy/rebuild", {}))}
            disabled={busy}
            className="btn-ghost py-1 text-xs"
          >
            Rebuild the index
          </button>
        </header>
        {queue.length === 0 ? (
          <p className="py-10 text-sm text-muted-foreground">
            Nothing waiting. Names appear here once they have come up in a few posts.
          </p>
        ) : (
          <ul className="rows">
            {queue.map((c) => (
              <li key={c.id} className="row items-center" style={{ "--state-w": "9rem" } as React.CSSProperties}>
                <span className="row-margin">
                  <span
                    className="h-[0.4375rem] w-[0.4375rem] shrink-0 rounded-full"
                    style={{ background: toneVar(c.dimension) }}
                    aria-hidden
                  />
                  <span className="truncate">{c.dimension}</span>
                </span>
                <span className="row-body flex flex-wrap items-center gap-x-3 gap-y-1.5">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[0.9375rem] font-medium">{c.name}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      In {c.count} posts
                      {c.surface_forms.length > 1
                        ? `, written as ${c.surface_forms.slice(0, 3).join(", ")}`
                        : ""}
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
                  Ignore
                </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-10">
        <header className="border-b pb-2.5">
          <h2 className="text-[0.9375rem] font-medium">Everything in the index</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Hiding or merging a tag sticks: a later rebuild will not undo it.
          </p>
        </header>
        <ul className="divide-y">
          {tags.map((t) => (
            <li key={t.slug} className="flex flex-wrap items-center gap-3 py-2.5">
              <span
                className="h-[0.4375rem] w-[0.4375rem] shrink-0 rounded-full"
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
                  <option value="">Merge into…</option>
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
                  Merge
                </button>
              )}
              <button
                onClick={() => void run(`Hid “${t.name}”.`, () => patch(`/api/studio/tags/${t.slug}`, { hidden: true }))}
                disabled={busy}
                className="link-quiet text-xs"
              >
                Hide
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
