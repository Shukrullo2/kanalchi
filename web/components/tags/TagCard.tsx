import Link from "next/link";
import { tierOf } from "@/lib/dimensions";
import { initialsTone } from "@/lib/format";
import { tagLabel } from "@/lib/labels";
import type { TagOut } from "@/lib/types";

/**
 * One subject in the index, as a card.
 *
 * The picture is the subject's own where we could find one — an organisation's
 * site icon, a person's portrait — and otherwise a post it appeared in, and
 * otherwise its initial on a flat tone, so the grid stays even rather than
 * going ragged.
 *
 * A logo and a photograph want opposite treatment: a photo should fill the
 * frame, while a logo is drawn to sit whole on white, so cropping it to fill or
 * dropping a dark wordmark onto navy loses the thing. `data-fit` carries that
 * distinction to the stylesheet.
 */
export function TagCard({
  tag,
  locale,
  countLabel,
}: {
  tag: TagOut;
  locale: string;
  /** Already pluralised by the page, e.g. "12 posts" / "12 ta post". */
  countLabel: string;
}) {
  const label = tagLabel(tag, locale);
  const { initials, style } = initialsTone(label);

  return (
    <Link href={`/tag/${tag.slug}`} className="tag-card" data-tier={tierOf(tag.dimension)}>
      <span className="tag-card-media" data-fit={tag.image_source?.startsWith("logo") ? tag.image_source : "photo"}>
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
        <span className="tag-card-count">{countLabel}</span>
      </span>
    </Link>
  );
}
