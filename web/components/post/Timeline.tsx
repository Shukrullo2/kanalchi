"use client";

import { useState } from "react";
import type { PostOut, PostPage } from "@/lib/types";
import { PostCard } from "./PostCard";

export function Timeline({ initial, loadMoreLabel }: { initial: PostPage; loadMoreLabel: string }) {
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
      {items.map((p) => (
        <PostCard key={p.id} post={p} />
      ))}
      {cursor ? (
        <button onClick={more} disabled={busy} className="mt-6 w-full rounded-lg border py-2 text-sm hover:bg-muted">
          {busy ? "…" : loadMoreLabel}
        </button>
      ) : null}
    </div>
  );
}
