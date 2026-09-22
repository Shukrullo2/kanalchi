import Link from "next/link";
import { tierOf } from "@/lib/dimensions";
import { initialsTone } from "@/lib/format";
import { tagLabel } from "@/lib/labels";
import type { TagOut } from "@/lib/types";

/**
 * One subject in the index, as a card.
 *
 * The picture is borrowed from the most-read post carrying the tag — a tag has
 * no image of its own, and the thing the channel published about it is a better
 * cue than a name alone. About two in five have one; the rest get their initial
 * on a flat tone, so the grid stays even rather than going ragged.
 */
export function TagCard({ tag, locale }: { tag: TagOut; locale: string }) {
  const label = tagLabel(tag, locale);
  const { initials, style } = initialsTone(label);

  return (
    <Link href={`/tag/${tag.slug}`} className="tag-card" data-tier={tierOf(tag.dimension)}>
      <span className="tag-card-media">
        {tag.thumb_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- served from MinIO on this domain
          <img src={tag.thumb_url} alt="" loading="lazy" />
        ) : (
          <span className="tag-card-initials" style={style} aria-hidden>
            {initials}
          </span>
        )}
      </span>
      <span className="tag-card-body">
        <span className="tag-card-name">{label}</span>
        <span className="tag-card-count">{tag.post_count}</span>
      </span>
    </Link>
  );
}
