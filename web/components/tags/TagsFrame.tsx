"use client";

import Link from "@/components/AppLink";
import { useMemo, useState, type ReactNode } from "react";
import { PanelToggle } from "@/components/graph/PanelToggle";
import { usePanel } from "@/components/graph/usePanel";
import { SearchIcon } from "@/components/Icons";
import "@/components/graph/graph.css";
import "./tags-frame.css";

export type FrameTag = { slug: string; label: string; count: number; tier: string };

/**
 * The index as a canvas: the cloud takes the whole viewport under the floating
 * header, and the group tabs, the group's description and a search field live
 * in a floating panel that can be put away — the same frame as the map.
 *
 * The cloud itself stays a server-rendered set of links (crawlable, and every
 * word a real URL); this only draws the frame round it. Search looks through
 * the whole group, not just the fifty words the cloud has room for, which is
 * the one thing the cloud cannot do on its own.
 */
export function TagsFrame({
  title,
  countLabel,
  description,
  tags,
  tabs,
  labels,
  children,
}: {
  title: string;
  /** Already formatted, e.g. "233 ta mavzu". */
  countLabel: string;
  description: string;
  tags: FrameTag[];
  tabs: ReactNode;
  labels: { search: string; noMatch: string; filter: string; groups: string; show: string; hide: string };
  children: ReactNode;
}) {
  const { open, toggle } = usePanel("kanalchi.tags.panel");
  const [q, setQ] = useState("");
  const needle = q.trim().toLowerCase();
  const matches = useMemo(
    () => (needle ? tags.filter((t) => t.label.toLowerCase().includes(needle) || t.slug.includes(needle)).slice(0, 40) : []),
    [tags, needle],
  );

  return (
    <div className="tags-frame" data-open={open}>
      <div className="tags-stage">
        <div className="tags-stage-inner">{children}</div>
      </div>

      <PanelToggle open={open} onToggle={toggle} controls="tags-controls" showLabel={labels.show} hideLabel={labels.hide} />

      <aside id="tags-controls" className="graph-controls" data-open={open} aria-label={title}>
        <header className="graph-controls-head">
          <span className="graph-controls-title">{title}</span>
          <span className="graph-count tnum">{countLabel}</span>
        </header>

        <details open>
          <summary>{labels.filter}</summary>
          <label className="search-field graph-search">
            <SearchIcon size={16} className="shrink-0 text-muted-foreground" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={labels.search} aria-label={labels.search} />
          </label>
          {needle ? (
            matches.length ? (
              <ul className="tags-frame-results">
                {matches.map((t) => (
                  <li key={t.slug}>
                    <Link href={`/tag/${t.slug}`} data-tier={t.tier}>
                      <i aria-hidden />
                      <span>{t.label}</span>
                      <b className="tnum">{t.count}</b>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="graph-hint">{labels.noMatch}</p>
            )
          ) : null}
        </details>

        <details open>
          <summary>{labels.groups}</summary>
          <p className="tags-frame-about">{description}</p>
          <div className="tags-frame-tabs">{tabs}</div>
        </details>
      </aside>
    </div>
  );
}
