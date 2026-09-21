"use client";

import { useLocale } from "next-intl";
import { useState } from "react";
import { monthKey, monthTitle } from "@/lib/format";
import type { PostOut, PostPage } from "@/lib/types";
import { PostEntry } from "./PostEntry";

/**
 * The register. Entries run in date order under a marker for the month they
 * belong to; the marker sticks while its own month scrolls past, so you always
 * know where in the archive you are.
 */
export function Timeline({ initial, loadMoreLabel }: { initial: PostPage; loadMoreLabel: string }) {
  const locale = useLocale();
  const [items, setItems] = useState<PostOut[]>(initial.items);
  const [cursor, setCursor] = useState<string | null>(initial.next_cursor);
  const [busy, setBusy] = useState(false);

  async function more() {
    if (!cursor || busy) return;
    setBusy(true);
    try {
      const res = await fetch(`/api/posts?cursor=${encodeURIComponent(cursor)}`);
      const page: PostPage = await res.json();
      setItems((prev) => [...prev, ...page.items]);
      setCursor(page.next_cursor);
    } finally {
      setBusy(false);
    }
  }

  const runs = groupByMonth(items);

  return (
    <div>
      {runs.map((run) => (
        <section key={run.key} className="register">
          <h2 className="month-mark">
            <span suppressHydrationWarning>{monthTitle(run.items[0].date, locale)}</span>
          </h2>
          {run.items.map((post) => (
            <PostEntry key={post.id} post={post} locale={locale} />
          ))}
        </section>
      ))}

      {cursor ? (
        <button onClick={more} disabled={busy} className="btn-ghost mt-6 w-full justify-center">
          {busy ? "…" : loadMoreLabel}
        </button>
      ) : null}
    </div>
  );
}

function groupByMonth(items: PostOut[]): { key: string; items: PostOut[] }[] {
  const runs: { key: string; items: PostOut[] }[] = [];
  for (const post of items) {
    const key = monthKey(post.date);
    const last = runs[runs.length - 1];
    if (last && last.key === key) last.items.push(post);
    else runs.push({ key, items: [post] });
  }
  return runs;
}
