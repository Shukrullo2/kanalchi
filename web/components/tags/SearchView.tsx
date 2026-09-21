"use client";

import { useState, useTransition } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CloseIcon, SearchIcon } from "@/components/Icons";
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

  function toggleTag(slug: string) {
    const next = new URLSearchParams(params.toString());
    const current = next.getAll("tags");
    next.delete("tags");
    const updated = current.includes(slug) ? current.filter((t) => t !== slug) : [...current, slug];
    updated.forEach((t) => next.append("tags", t));
    push(next);
  }

  return (
    <div className="space-y-5">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const next = new URLSearchParams(params.toString());
          if (q) next.set("q", q);
          else next.delete("q");
          push(next);
        }}
        className="relative"
      >
        <SearchIcon size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={labels.search}
          autoComplete="off"
          className="input-field py-3 pl-10 pr-4 text-base"
        />
      </form>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
        <span className="text-muted-foreground">{labels.sortBy}</span>
        <div className="flex items-center rounded-full bg-surface-2 p-0.5">
          {SORTS.map((s) => (
            <button
              key={s}
              onClick={() => {
                const next = new URLSearchParams(params.toString());
                next.set("sort", s);
                push(next);
              }}
              className={`rounded-full px-2.5 py-1 transition-colors ${
                s === sort ? "bg-surface font-medium shadow-xs" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        {activeTags.length > 0 ? (
          <button onClick={() => push(new URLSearchParams(q ? { q } : {}))} className="link-quiet ml-auto underline">
            {labels.clear}
          </button>
        ) : null}
      </div>

      {activeTags.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {activeTags.map((slug) => (
            <button key={slug} onClick={() => toggleTag(slug)} className="tag-pill" data-active="true">
              {slug}
              <CloseIcon size={11} />
            </button>
          ))}
        </div>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[1fr_190px]">
        <div className={`space-y-3.5 transition-opacity ${pending ? "opacity-40" : ""}`}>
          {initial.items.length === 0 ? (
            <div className="card-surface p-12 text-center text-sm text-muted-foreground">{labels.nothing}</div>
          ) : (
            initial.items.map((p) => <PostCard key={p.id} post={p} locale={locale} />)
          )}
        </div>

        {Object.keys(initial.facets ?? {}).length > 0 ? (
          <aside className="order-first space-y-4 lg:order-last">
            {Object.entries(initial.facets ?? {}).map(([dimension, tags]) => (
              <div key={dimension}>
                <div className="mb-1.5 flex items-center gap-1.5 text-[0.65rem] uppercase tracking-wider text-muted-foreground">
                  <span
                    className="inline-block h-1.5 w-1.5 rounded-full"
                    style={{ background: `var(--dim-${dimension}, var(--dim-default))` }}
                    aria-hidden
                  />
                  {dimension}
                </div>
                <ul className="space-y-0.5">
                  {tags.slice(0, 8).map((t) => (
                    <li key={t.slug}>
                      <button
                        onClick={() => toggleTag(t.slug)}
                        className={`flex w-full items-baseline justify-between gap-2 rounded px-1.5 py-1 text-left text-sm transition-colors hover:bg-surface-2 ${
                          activeTags.includes(t.slug) ? "font-medium text-foreground" : "text-muted-foreground"
                        }`}
                      >
                        <span className="truncate">{tagLabel(t, locale)}</span>
                        <span className="shrink-0 text-xs tabular-nums opacity-60">{t.count}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </aside>
        ) : null}
      </div>
    </div>
  );
}
