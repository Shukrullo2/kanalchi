import Link from "next/link";
import { tagLabel } from "@/lib/labels";
import type { TagOut } from "@/lib/types";

/** Tag pill tinted by its dimension, so the kind of tag is readable without labels. */
export function TagChip({
  tag,
  locale,
  showCount = false,
  active = false,
}: {
  tag: Pick<TagOut, "slug" | "name" | "labels" | "dimension" | "post_count">;
  locale: string;
  showCount?: boolean;
  active?: boolean;
}) {
  return (
    <Link
      href={`/tag/${tag.slug}`}
      className="tag-pill"
      data-active={active}
      style={{ "--tone": `var(--dim-${tag.dimension ?? "default"}, var(--dim-default))` } as React.CSSProperties}
    >
      {tagLabel(tag, locale)}
      {showCount ? <span className="tag-count">{tag.post_count}</span> : null}
    </Link>
  );
}
