import Link from "next/link";
import { EyeIcon } from "@/components/Icons";
import { TagRef } from "@/components/tags/TagChip";
import { byTier, tierOf } from "@/lib/dimensions";
import { compactNumber, fullDate, postDate } from "@/lib/format";
import type { PostOut } from "@/lib/types";
import { MediaGallery } from "./MediaGallery";

/**
 * One entry in the register: the date in the margin, the post beside it.
 *
 * The margin is the point of the whole layout — in an archive of twenty thousand
 * messages, when a thing was said is half of what you are looking for, so the
 * dates line up in a column you can run your eye down instead of being buried in
 * a metadata strip under each post.
 */
export function PostEntry({
  post,
  locale,
  rank,
}: {
  post: PostOut;
  locale: string;
  /** Position in a ranked list. It goes in the margin, where ordinals belong. */
  rank?: number;
}) {
  const body = post.html ?? post.text;
  // Only the tags a reader scans by. Language, media kind and post format are
  // filing details; they belong on the post's own page, not in the timeline.
  const subjects = byTier(post.tags ?? []).filter((t) => tierOf(t.dimension) !== "meta").slice(0, 5);

  return (
    <article className="entry">
      <div className="entry-margin">
        {rank ? <span className="entry-rank tnum">{rank}</span> : null}
        <Link
          href={`/post/${post.id}`}
          className="entry-day hover:underline"
          title={fullDate(post.date, locale)}
        >
          <time dateTime={post.date} suppressHydrationWarning>
            {postDate(post.date, locale)}
          </time>
        </Link>
        {post.views > 0 ? (
          <span className="flex items-center gap-1 whitespace-nowrap">
            <EyeIcon size={12} />
            {compactNumber(post.views)}
          </span>
        ) : null}
      </div>

      <div className="entry-body">
        {post.forward_from ? (
          <p className="mb-2 text-xs text-muted-foreground">
            forwarded from {post.forward_from.title ?? post.forward_from.username ?? "a channel"}
          </p>
        ) : null}

        {post.media.length > 0 ? (
          <div className="mb-3">
            <MediaGallery media={post.media} />
          </div>
        ) : null}

        {body ? (
          <div className="tg-body whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: body }} />
        ) : null}

        {post.truncated ? (
          <Link href={`/post/${post.id}`} className="mt-1 inline-block text-sm text-primary hover:underline">
            Read the rest
          </Link>
        ) : null}

        {post.poll ? <Poll poll={post.poll} /> : null}

        {subjects.length > 0 ? (
          <div className="mt-3 flex flex-wrap items-center gap-x-3.5 gap-y-1.5">
            {subjects.map((tag) => (
              <TagRef key={tag.slug} tag={tag} locale={locale} />
            ))}
          </div>
        ) : null}
      </div>
    </article>
  );
}

function Poll({ poll }: { poll: NonNullable<PostOut["poll"]> }) {
  const total = poll.total_voters || 0;
  return (
    <div className="mt-3 max-w-md">
      <div className="text-sm font-medium">{poll.question}</div>
      <ul className="mt-2 space-y-1.5">
        {poll.answers.map((a, i) => {
          const share = total ? Math.round(((a.voters ?? 0) / total) * 100) : 0;
          return (
            <li key={i} className="text-sm">
              <div className="flex justify-between gap-4">
                <span>{a.text}</span>
                <span className="tnum text-muted-foreground">{share}%</span>
              </div>
              <div className="mt-1 h-[3px] overflow-hidden rounded-full bg-border">
                <div className="h-full rounded-full bg-primary" style={{ width: `${share}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
