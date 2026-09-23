"use client";

import type { TaxonomyPreview } from "@/lib/types";

/** What applying an index proposal would change, per dimension. Labels come from the caller so the
 *  same panel serves the English console and the localized studio. */
export function ProposalPreview({
  preview,
  locale,
  words,
}: {
  preview: TaxonomyPreview;
  locale: string;
  words: { newTags: (n: number) => string; keptTags: (n: number) => string; droppedTags: (n: number) => string };
}) {
  return (
    <ul className="divide-y text-sm">
      {preview.dimensions.map((d) => (
        <li key={d.key} className="py-2">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="font-medium">{d.labels[locale] ?? d.labels.en ?? d.key}</span>
            <span className="text-xs tabular-nums text-muted-foreground">
              {words.newTags(d.new_count)} · {words.keptTags(d.kept_count)} · {words.droppedTags(d.dropped_count)}
            </span>
          </div>
          {d.new.length > 0 ? (
            <p className="mt-1 text-xs text-muted-foreground">
              {d.new.slice(0, 40).join(", ")}
              {d.new_count > 40 ? " …" : ""}
            </p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
