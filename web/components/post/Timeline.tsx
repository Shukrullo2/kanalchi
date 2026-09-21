"use client";

import { useLocale } from "next-intl";
import { useState } from "react";
import type { PostOut, PostPage } from "@/lib/types";
import { PostCard } from "./PostCard";

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
    <div className="space-y-3.5">
      {items.map((p, i) => (
        <div key={p.id} className="animate-rise" style={{ animationDelay: `${Math.min(i, 8) * 25}ms` }}>
          <PostCard post={p} locale={locale} />
        </div>
      ))}
      {cursor ? (
        <button onClick={more} disabled={busy} className="btn-ghost w-full justify-center">
          {busy ? <span className="animate-pulse">…</span> : loadMoreLabel}
        </button>
      ) : null}
    </div>
  );
}
