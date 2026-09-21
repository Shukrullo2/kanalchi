import Link from "next/link";
import { tierOf } from "@/lib/dimensions";
import { tagLabel } from "@/lib/labels";
import type { TagOut } from "@/lib/types";

type Tag = Pick<TagOut, "slug" | "name" | "labels" | "dimension" | "post_count">;

/**
 * Inline form, for the tags under a post: a word with a tone dot. Eight of these
 * in a row still read as a line of text.
 */
export function TagRef({ tag, locale }: { tag: Tag; locale: string }) {
  return (
    <Link href={`/tag/${tag.slug}`} className="tag" data-tier={tierOf(tag.dimension)}>
      {tagLabel(tag, locale)}
    </Link>
  );
}

/**
 * Pill form, for pages where tags are the thing you are aiming at. Bigger hit
 * area, a count when the count is the point.
 */
export function TagChip({
  tag,
  locale,
  showCount = false,
  active = false,
}: {
  tag: Tag;
  locale: string;
  showCount?: boolean;
  active?: boolean;
}) {
  return (
    <Link
      href={`/tag/${tag.slug}`}
      className="tag-pill"
      data-tier={tierOf(tag.dimension)}
      data-active={active}
    >
      {tagLabel(tag, locale)}
      {showCount ? <span className="tag-count">{tag.post_count}</span> : null}
    </Link>
  );
}
