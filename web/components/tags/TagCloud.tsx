import Link from "next/link";
import { tierOf } from "@/lib/dimensions";
import { tagLabel } from "@/lib/labels";
import type { TagOut } from "@/lib/types";

/**
 * One group of the index, as a cloud of words.
 *
 * Size is the measure. A subject the channel returns to every week is set
 * large, one it mentioned twice is small, and the whole group can be taken in
 * at a glance without reading a single number — which is the thing a ranked
 * list of names never manages.
 *
 * The scale is logarithmic because the counts are. This channel's largest
 * subject has 650 posts and its median has 4; on a linear scale everything but
 * the top few would collapse into the same smallest size.
 *
 * Words are in alphabetical order rather than by size. Sorting by size would
 * lay them out as a staircase, which reads as a list; interleaving the sizes is
 * what makes a cloud a cloud, and it lets the group double as an A-Z for
 * finding a subject you already have in mind.
 */
export function TagCloud({ tags, locale }: { tags: TagOut[]; locale: string }) {
  const counts = tags.map((t) => t.post_count);
  const low = Math.log(Math.min(...counts) + 1);
  const high = Math.log(Math.max(...counts) + 1);
  // Everything in the group having the same count is rare but real; give them
  // all the middle size rather than dividing by zero.
  const weight = (count: number) =>
    high === low ? 0.5 : (Math.log(count + 1) - low) / (high - low);

  const sorted = [...tags].sort((a, b) =>
    tagLabel(a, locale).localeCompare(tagLabel(b, locale), locale),
  );

  return (
    <div className="tag-cloud">
      {sorted.map((tag) => (
        <Link
          key={tag.slug}
          href={`/tag/${tag.slug}`}
          className="tag-word"
          data-tier={tierOf(tag.dimension)}
          style={{ "--w": weight(tag.post_count).toFixed(3) } as React.CSSProperties}
        >
          {tagLabel(tag, locale)}
          <span className="tag-word-count">{tag.post_count}</span>
        </Link>
      ))}
    </div>
  );
}
