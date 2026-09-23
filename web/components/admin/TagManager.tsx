"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { call, patch, post } from "@/lib/client";
import { toneVar } from "@/lib/dimensions";
import { tagLabel } from "@/lib/labels";
import type { PendingTag, TagOut } from "@/lib/types";

/**
 * Curating a channel's index: names that keep coming up but are not tags yet, the live
 * tags (merge, hide), and the hidden ones (show again). Every edit here pins the tag, so
 * a later rebuild keeps the decision. Labels are shown in the channel's primary language.
 */
export function TagManager({
  tenantId,
  pending,
  tags,
  hidden,
  locale,
  groups,
}: {
  tenantId: number;
  pending: PendingTag[];
  tags: TagOut[];
  hidden: TagOut[];
  /** The channel's primary language, which is what the tag labels are read in. */
  locale: string;
  /** Dimension key -> the group's name. */
  groups: Record<string, string>;
}) {
  const router = useRouter();
  const base = `/api/admin/tenants/${tenantId}`;
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
      setQueue(await call<PendingTag[]>(`${base}/tags/pending`));
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
          <div>
            <h2 className="text-[0.9375rem] font-medium">Names waiting to be filed</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Found repeatedly in the posts but not in the index. The fifty most frequent; the list refills as you go.
            </p>
          </div>
          <button
            onClick={() => void run("Rebuild queued — it proposes a new version for review.", () => post(`${base}/taxonomy/rebuild`))}
            disabled={busy}
            className="btn-ghost py-1 text-xs"
          >
            Rebuild the index
          </button>
        </header>
        {queue.length === 0 ? (
          <p className="py-10 text-sm text-muted-foreground">Nothing waiting. Names appear here once they have come up in a few posts.</p>
        ) : (
          <ul className="rows">
            {queue.map((c) => (
              <li key={c.id} className="row items-center" style={{ "--state-w": "9rem" } as React.CSSProperties}>
                <span className="row-margin">
                  <span className="h-[0.4375rem] w-[0.4375rem] shrink-0 rounded-full" style={{ background: toneVar(c.dimension) }} aria-hidden />
                  <span className="truncate">{groups[c.dimension] ?? c.dimension}</span>
                </span>
                <span className="row-body flex flex-wrap items-center gap-x-3 gap-y-1.5">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[0.9375rem] font-medium">{c.name}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      In {c.count} posts
                      {c.surface_forms.length > 0 ? `, written as ${c.surface_forms.slice(0, 3).join(", ")}` : ""}
                    </span>
                  </span>
                  <button
                    onClick={() => void run(`Added “${c.name}”.`, () => post(`${base}/tags/pending/${c.id}/promote`))}
                    disabled={busy}
                    className="btn-primary py-1 text-xs"
                  >
                    Add as tag
                  </button>
                  <button
                    onClick={() => void run("Dismissed.", () => post(`${base}/tags/pending/${c.id}/reject`))}
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
          {tags.map((tag) => (
            <li key={tag.slug} className="flex flex-wrap items-center gap-3 py-2.5">
              <span className="h-[0.4375rem] w-[0.4375rem] shrink-0 rounded-full" style={{ background: toneVar(tag.dimension) }} aria-hidden />
              <span className="min-w-0 flex-1 truncate text-sm">{tagLabel(tag, locale)}</span>
              <span className="shrink-0 text-xs text-muted-foreground">{groups[tag.dimension ?? ""] ?? tag.dimension}</span>
              <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{tag.post_count}</span>
              {mergeFrom === tag.slug ? (
                <select
                  autoFocus
                  className="input-field w-auto py-1 text-xs"
                  onChange={(e) => {
                    const into = e.target.value;
                    if (into) void run(`Merged into ${into}.`, () => post(`${base}/tags/${tag.slug}/merge`, { into }));
                    setMergeFrom(null);
                  }}
                  defaultValue=""
                >
                  <option value="">Merge into…</option>
                  {tags
                    .filter((o) => o.slug !== tag.slug && o.dimension === tag.dimension)
                    .map((o) => (
                      <option key={o.slug} value={o.slug}>
                        {tagLabel(o, locale)}
                      </option>
                    ))}
                </select>
              ) : (
                <button onClick={() => setMergeFrom(tag.slug)} className="link-quiet text-xs">
                  Merge
                </button>
              )}
              <button
                onClick={() => void run(`Hid “${tag.name}”.`, () => patch(`${base}/tags/${tag.slug}`, { hidden: true }))}
                disabled={busy}
                className="link-quiet text-xs"
              >
                Hide
              </button>
            </li>
          ))}
        </ul>
      </section>

      {hidden.length > 0 ? (
        <section className="mt-10">
          <header className="border-b pb-2.5">
            <h2 className="text-[0.9375rem] font-medium">Hidden from readers</h2>
          </header>
          <ul className="divide-y">
            {hidden.map((tag) => (
              <li key={tag.slug} className="flex flex-wrap items-center gap-3 py-2.5">
                <span className="h-[0.4375rem] w-[0.4375rem] shrink-0 rounded-full opacity-50" style={{ background: toneVar(tag.dimension) }} aria-hidden />
                <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">{tagLabel(tag, locale)}</span>
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{tag.post_count}</span>
                <button
                  onClick={() => void run(`“${tag.name}” is back in the index.`, () => patch(`${base}/tags/${tag.slug}`, { hidden: false }))}
                  disabled={busy}
                  className="link-quiet text-xs"
                >
                  Show again
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
