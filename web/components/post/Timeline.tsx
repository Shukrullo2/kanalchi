"use client";

import { useLocale } from "next-intl";
import { useState } from "react";
import type { PostOut, PostPage } from "@/lib/types";
import { PostEntry } from "./PostEntry";

/** The archive as a grid of cards, with a button to pull the next page in. */
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

  return (
    <div>
      <div className="archive-grid">
        {items.map((post) => (
          <PostEntry key={post.id} post={post} locale={locale} />
        ))}
      </div>

      {cursor ? (
        <div className="mt-8 flex justify-center">
          <button onClick={more} disabled={busy} className="btn-ghost px-8">
            {busy ? "…" : loadMoreLabel}
          </button>
        </div>
      ) : null}
    </div>
  );
}
