"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { CloseIcon, SearchIcon } from "@/components/Icons";
import { PostEntry } from "@/components/post/PostEntry";
import { tagLabel } from "@/lib/labels";
import type { PostOut, SearchResult } from "@/lib/types";
import { toneVar } from "@/lib/dimensions";

const SORTS = ["relevance", "newest", "oldest", "views", "reactions"] as const;
const PERIODS = ["", "30d", "1y"] as const;
const TYPES = ["", "none", "photo", "album", "video"] as const;
/** Tags shown per group before "more"; the API sends up to twelve. */
const FOLD = 5;
/** Groups open on arrival; the rest are one click away. */
const OPEN_GROUPS = 3;

export type SearchFilters = { q: string; tags: string[]; sort: string; period: string; type: string };

type Labels = {
  search: string;
  nothing: string;
  sortBy: string;
  clear: string;
  sorts: Record<(typeof SORTS)[number], string>;
  period: string;
  periods: Record<(typeof PERIODS)[number], string>;
  type: string;
  types: Record<(typeof TYPES)[number], string>;
  filters: string;
  results: string;
  resultsCapped: string;
  /** "yana {count}": filled in here, per group. */
  moreTemplate: string;
  less: string;
  loadMore: string;
};

/**
 * Search with its filters in one panel: period, post type and the subjects the
 * matches are filed under, counted over everything that matched rather than the
 * page on screen. The URL is the state, so a filtered search can be shared; the
 * server renders the first page and "load more" asks the API for the next ones.
 */
export function SearchView({
  initial,
  query,
  filters,
  years,
  locale,
  labels,
  groups,
  tagNames,
}: {
  initial: SearchResult;
  /** The API query string the first page was fetched with; later pages add an offset. */
  query: string;
  filters: SearchFilters;
  /** Years the archive covers, newest first. */
  years: number[];
  locale: string;
  /** Dimension key -> the group's name in the reader's language, for the facet headings. */
  groups: Record<string, string>;
  /** Slug -> tag name, for the filter chips, which the URL only gives us as slugs. */
  tagNames: Record<string, string>;
  labels: Labels;
}) {
  const router = useRouter();
  const [q, setQ] = useState(filters.q);
  const [pending, startTransition] = useTransition();
  const [items, setItems] = useState<PostOut[]>(initial.items);
  const [hasMore, setHasMore] = useState(initial.has_more);
  const [loading, setLoading] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  // A new search arrives as new props rather than a remount, so the filter panel stays open
  // on a phone while several filters are picked; the loaded pages restart from the new first page.
  const [shown, setShown] = useState({ initial, q: filters.q });
  if (shown.initial !== initial) {
    setShown({ initial, q: filters.q });
    setItems(initial.items);
    setHasMore(initial.has_more);
    if (shown.q !== filters.q) setQ(filters.q);
  }

  const facets = Object.entries(initial.facets ?? {});
  const activeCount = filters.tags.length + (filters.period ? 1 : 0) + (filters.type ? 1 : 0);

  function go(change: Partial<SearchFilters>) {
    const next = { ...filters, q, ...change };
    const params = new URLSearchParams();
    if (next.q.trim()) params.set("q", next.q.trim());
    if (next.sort && next.sort !== "relevance") params.set("sort", next.sort);
    if (next.period) params.set("period", next.period);
    if (next.type) params.set("type", next.type);
    next.tags.forEach((t) => params.append("tags", t));
    const qs = params.toString();
    startTransition(() => router.push(qs ? `/search?${qs}` : "/search", { scroll: false }));
  }

  const toggleTag = (slug: string) =>
    go({ tags: filters.tags.includes(slug) ? filters.tags.filter((t) => t !== slug) : [...filters.tags, slug] });

  async function loadMore() {
    setLoading(true);
    try {
      const res = await fetch(`/api/search?${query}&limit=20&offset=${items.length}&with_facets=false`);
      if (!res.ok) throw new Error(String(res.status));
      const page = (await res.json()) as SearchResult;
      setItems((prev) => [...prev, ...page.items.filter((p) => !prev.some((x) => x.id === p.id))]);
      setHasMore(page.has_more);
    } catch {
      setHasMore(false);
    } finally {
      setLoading(false);
    }
  }

  const periodName = (p: string) => (p in labels.periods ? labels.periods[p as keyof Labels["periods"]] : p);

  const panel = (
    <div className="search-filters">
      <section>
        <h2>{labels.period}</h2>
        <div className="search-options">
          {[...PERIODS, ...years.map(String)].map((p) => (
            <button key={p || "all"} type="button" data-active={filters.period === p} onClick={() => go({ period: p })}>
              {periodName(p)}
            </button>
          ))}
        </div>
      </section>

      <section>
        <h2>{labels.type}</h2>
        <div className="search-options">
          {TYPES.map((k) => (
            <button key={k || "all"} type="button" data-active={filters.type === k} onClick={() => go({ type: k })}>
              {labels.types[k]}
            </button>
          ))}
        </div>
      </section>

      {facets.map(([dimension, tags], i) => {
        const open = expanded.has(dimension);
        const visible = open ? tags : tags.slice(0, FOLD);
        // A chosen tag stays visible even when it ranks below the fold.
        const hiddenChosen = open ? [] : tags.slice(FOLD).filter((t) => filters.tags.includes(t.slug));
        return (
          <details key={dimension} open={i < OPEN_GROUPS || tags.some((t) => filters.tags.includes(t.slug))}>
            <summary>
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: toneVar(dimension) }} aria-hidden />
              {groups[dimension] ?? dimension}
            </summary>
            <ul>
              {[...visible, ...hiddenChosen].map((t) => {
                const on = filters.tags.includes(t.slug);
                return (
                  <li key={t.slug}>
                    <button type="button" aria-pressed={on} data-active={on} onClick={() => toggleTag(t.slug)}>
                      <span className="search-check" aria-hidden />
                      <span className="min-w-0 flex-1 truncate">{tagLabel(t, locale)}</span>
                      <span className="shrink-0 tabular-nums opacity-60">{t.count}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
            {tags.length > FOLD ? (
              <button
                type="button"
                className="search-more"
                onClick={() =>
                  setExpanded((prev) => {
                    const next = new Set(prev);
                    if (next.has(dimension)) next.delete(dimension);
                    else next.add(dimension);
                    return next;
                  })
                }
              >
                {open ? labels.less : labels.moreTemplate.replace("{count}", String(tags.length - FOLD))}
              </button>
            ) : null}
          </details>
        );
      })}
    </div>
  );

  const total = initial.total ?? initial.count;

  return (
    <div className="space-y-5">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          go({ q });
        }}
        className="relative"
      >
        <SearchIcon size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={labels.search}
          autoComplete="off"
          enterKeyHint="search"
          className="input-field py-3 pl-10 pr-4 text-base"
        />
      </form>

      <button
        type="button"
        className="btn-ghost h-8 px-3 text-xs lg:hidden"
        aria-expanded={showFilters}
        aria-controls="search-filters"
        onClick={() => setShowFilters((v) => !v)}
      >
        {labels.filters}
        {activeCount ? <span className="search-count">{activeCount}</span> : null}
      </button>

      <div className="grid gap-6 lg:grid-cols-[15.5rem_minmax(0,1fr)]">
        <aside className={`${showFilters ? "block" : "hidden"} lg:block`} id="search-filters">
          <div className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto lg:pr-1">{panel}</div>
        </aside>

        <div className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
            <span className="text-sm text-muted-foreground" aria-live="polite">
              {total ? (initial.total_capped ? labels.resultsCapped : labels.results) : null}
            </span>
            <div className="ml-auto flex items-center gap-2">
              <span className="hidden text-muted-foreground sm:inline">{labels.sortBy}</span>
              <div className="flex flex-wrap items-center rounded-full bg-surface-2 p-0.5">
                {SORTS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => go({ sort: s })}
                    className={`rounded-full px-2.5 py-1 transition-colors ${
                      s === filters.sort ? "bg-surface font-medium shadow-xs" : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {labels.sorts[s]}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {activeCount > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5">
              {filters.period ? (
                <button type="button" onClick={() => go({ period: "" })} className="tag-pill" data-active="true">
                  {periodName(filters.period)}
                  <CloseIcon size={11} />
                </button>
              ) : null}
              {filters.type ? (
                <button type="button" onClick={() => go({ type: "" })} className="tag-pill" data-active="true">
                  {labels.types[filters.type as keyof Labels["types"]] ?? filters.type}
                  <CloseIcon size={11} />
                </button>
              ) : null}
              {filters.tags.map((slug) => (
                <button key={slug} type="button" onClick={() => toggleTag(slug)} className="tag-pill" data-active="true">
                  {tagNames[slug] ?? slug}
                  <CloseIcon size={11} />
                </button>
              ))}
              <button type="button" onClick={() => go({ tags: [], period: "", type: "" })} className="link-quiet ml-1 text-xs underline">
                {labels.clear}
              </button>
            </div>
          ) : null}

          <div className={`transition-opacity ${pending ? "opacity-40" : ""}`}>
            {items.length === 0 ? (
              <div className="py-16 text-center text-sm text-muted-foreground">{labels.nothing}</div>
            ) : (
              <div className="archive-grid archive-grid-narrow">
                {items.map((p) => (
                  <PostEntry key={p.id} post={p} locale={locale} />
                ))}
              </div>
            )}
          </div>

          {hasMore && items.length > 0 ? (
            <div className="flex justify-center pt-2">
              <button type="button" onClick={() => void loadMore()} disabled={loading} className="btn-ghost px-5">
                {loading ? "…" : labels.loadMore}
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
