"use client";

import Link from "@/components/AppLink";
import { tierOf } from "@/lib/dimensions";
import { compactNumber, postDate } from "@/lib/format";
import type { GNode } from "@/lib/graph";
import type { GraphPost, GraphTag } from "@/lib/types";

/**
 * What the map says about the thing you clicked. A post gets its details and
 * a way out to the post itself; a subject gets its posts in this period, so
 * the map is a way of reading the archive and not only of looking at it.
 */
export function NodePanel({
  node,
  posts,
  tags,
  locale,
  labelOf,
  dimensionLabel,
  inFilter,
  t,
  onToggleTag,
  onClose,
}: {
  node: GNode;
  /** Posts in the window that passed the filters. */
  posts: GraphPost[];
  tags: GraphTag[];
  locale: string;
  labelOf: (tag: GraphTag) => string;
  dimensionLabel: (key: string | null) => string;
  inFilter: boolean;
  t: (key: string, values?: Record<string, string | number>) => string;
  onToggleTag: (slug: string) => void;
  onClose: () => void;
}) {
  const title = node.kind === "post" ? node.post!.title : labelOf(node.tag!);
  return (
    <aside className="graph-panel" aria-label={title}>
      <header>
        <h3>{title}</h3>
        <button type="button" onClick={onClose} aria-label={t("close")}>
          ×
        </button>
      </header>
      <div className="graph-panel-body">
        {node.kind === "post" ? <PostBody post={node.post!} /> : <TagBody tag={node.tag!} />}
      </div>
    </aside>
  );

  function PostBody({ post }: { post: GraphPost }) {
    return (
      <>
        <div className="graph-meta" suppressHydrationWarning>
          {postDate(post.date, locale)} · {t("views", { count: compactNumber(post.views) })}
          {post.reply !== null ? ` · ${t("replyTo", { id: String(post.reply) })}` : ""}
        </div>
        {post.tags.length > 0 ? (
          <div className="graph-panel-tags">
            {post.tags.map((i) => {
              const tag = tags[i];
              return (
                <button
                  key={tag.slug}
                  type="button"
                  className="tag-pill"
                  data-tier={tierOf(tag.dimension)}
                  onClick={() => onToggleTag(tag.slug)}
                >
                  {labelOf(tag)}
                </button>
              );
            })}
          </div>
        ) : null}
        <div className="graph-panel-actions">
          <Link href={`/post/${post.id}`} className="btn-primary">
            {t("openPost")}
          </Link>
        </div>
      </>
    );
  }

  function TagBody({ tag }: { tag: GraphTag }) {
    const index = tags.findIndex((x) => x.slug === tag.slug);
    const list = posts.filter((p) => p.tags.includes(index)).slice(0, 80);
    return (
      <>
        <div className="graph-meta">
          {dimensionLabel(tag.dimension)} · {t("inWindow", { count: String(list.length), total: String(tag.post_count) })}
        </div>
        <div className="graph-panel-actions">
          <button type="button" className="btn-primary" onClick={() => onToggleTag(tag.slug)}>
            {inFilter ? t("unfilter") : t("filterBy")}
          </button>
          <Link href={`/tag/${tag.slug}`} className="btn-ghost">
            {labelOf(tag)} →
          </Link>
        </div>
        <ul className="graph-panel-list">
          {list.map((p) => (
            <li key={p.id}>
              <span className="graph-meta" suppressHydrationWarning>
                {postDate(p.date, locale)}
              </span>
              <Link href={`/post/${p.id}`}>{p.title}</Link>
            </li>
          ))}
        </ul>
      </>
    );
  }
}
