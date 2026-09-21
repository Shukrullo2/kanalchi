"use client";

import { useState, useTransition } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PostCard } from "@/components/post/PostCard";
import { tagLabel } from "@/lib/labels";
import type { SearchResult } from "@/lib/types";

const SORTS = ["relevance", "newest", "oldest", "views", "reactions"] as const;

export function SearchView({
  initial,
  locale,
  labels,
}: {
  initial: SearchResult;
  locale: string;
  labels: { search: string; nothing: string; sortBy: string; clear: string };
}) {
  const router = useRouter();
  const params = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [pending, startTransition] = useTransition();

  const activeTags = params.getAll("tags");
  const sort = params.get("sort") ?? "relevance";

  function push(next: URLSearchParams) {
    startTransition(() => router.push(`/search?${next.toString()}`));
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const next = new URLSearchParams(params.toString());
    if (q) next.set("q", q);
    else next.delete("q");
    push(next);
  }

  function toggleTag(slug: string) {
    const next = new URLSearchParams(params.toString());
    const current = next.getAll("tags");
    next.delete("tags");
    const updated = current.includes(slug) ? current.filter((t) => t !== slug) : [...current, slug];
    updated.forEach((t) => next.append("tags", t));
    push(next);
  }

  function setSort(value: string) {
    const next = new URLSearchParams(params.toString());
    next.set("sort", value);
    push(next);
  }

  return (
    <div className="space-y-5">
      <form onSubmit={submit} className="flex gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={labels.search}
          className="flex-1 rounded-lg border bg-transparent px-3 py-2"
        />
        <button className="rounded-lg bg-foreground px-4 text-background">↵</button>
      </form>

      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span className="text-muted-foreground">{labels.sortBy}</span>
        {SORTS.map((s) => (
          <button
            key={s}
            onClick={() => setSort(s)}
            className={s === sort ? "font-semibold" : "text-muted-foreground hover:text-foreground"}
          >
            {s}
          </button>
        ))}
        {activeTags.length > 0 ? (
          <button onClick={() => push(new URLSearchParams(q ? { q } : {}))} className="ml-auto underline">
            {labels.clear}
          </button>
        ) : null}
      </div>

      {activeTags.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {activeTags.map((slug) => (
            <button
              key={slug}
              onClick={() => toggleTag(slug)}
              className="rounded-full bg-foreground px-2.5 py-0.5 text-xs text-background"
            >
              {slug} ×
            </button>
          ))}
        </div>
      ) : null}

      <div className="grid gap-6 sm:grid-cols-[1fr_200px]">
        <div className={pending ? "opacity-50" : undefined}>
          {initial.items.length === 0 ? (
            <p className="text-muted-foreground">{labels.nothing}</p>
          ) : (
            initial.items.map((p) => <PostCard key={p.id} post={p} />)
          )}
        </div>
        <aside className="order-first space-y-4 text-sm sm:order-last">
          {Object.entries(initial.facets ?? {}).map(([dimension, tags]) => (
            <div key={dimension}>
              <div className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">{dimension}</div>
              <ul className="space-y-0.5">
                {tags.slice(0, 8).map((t) => (
                  <li key={t.slug}>
                    <button
                      onClick={() => toggleTag(t.slug)}
                      className={`flex w-full justify-between gap-2 text-left hover:text-foreground ${
                        activeTags.includes(t.slug) ? "font-semibold" : "text-muted-foreground"
                      }`}
                    >
                      <span className="truncate">{tagLabel(t, locale)}</span>
                      <span>{t.count}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </aside>
      </div>
    </div>
  );
}
