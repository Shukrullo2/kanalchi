import Link from "@/components/AppLink";
import { byDimensionTier } from "@/lib/dimensions";
import { dimensionLabel } from "@/lib/labels";
import type { DimensionOut } from "@/lib/types";

/**
 * The groups an index is divided into, as one row of tabs.
 *
 * Each is a real URL rather than client state, so a group can be linked, shared
 * and found by a search engine. The row scrolls sideways on a phone; seventeen
 * groups will not wrap into something readable.
 */
export function DimensionTabs({
  dimensions,
  active,
  locale,
}: {
  dimensions: DimensionOut[];
  active: string;
  locale: string;
}) {
  return (
    <nav className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
      {byDimensionTier(dimensions).map((d) => (
        <Link
          key={d.key}
          href={`/tags/${d.key}`}
          className="pill shrink-0"
          data-active={d.key === active}
          aria-current={d.key === active ? "page" : undefined}
        >
          {dimensionLabel(d, locale)}
          <span className="tag-count">{d.tag_count}</span>
        </Link>
      ))}
    </nav>
  );
}
