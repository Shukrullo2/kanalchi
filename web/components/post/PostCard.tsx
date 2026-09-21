import { ExternalIcon, EyeIcon, ShareIcon } from "@/components/Icons";
import { compactNumber, fullDate } from "@/lib/format";
import type { PostOut } from "@/lib/types";
import { MediaGallery } from "./MediaGallery";
import { PostEntry } from "./PostEntry";

/**
 * A post on its own page. Everywhere else — timelines, tag pages, search results
 * — a post is a row in the register, so this delegates and only the single-post
 * view is written out here.
 */
export function PostCard({
  post,
  locale,
  full = false,
  rank,
}: {
  post: PostOut;
  locale: string;
  full?: boolean;
  rank?: number;
}) {
  if (!full) return <PostEntry post={post} locale={locale} rank={rank} />;

  const body = post.html ?? post.text;
  const reactions = post.reactions.filter((r) => r.emoji).slice(0, 6);

  return (
    <article>
      <div className="meta-row border-b pb-3">
        <time dateTime={post.date} suppressHydrationWarning className="text-foreground">
          {fullDate(post.date, locale)}
        </time>
        {post.views > 0 ? (
          <span className="flex items-center gap-1.5">
            <EyeIcon size={13} />
            {compactNumber(post.views)}
          </span>
        ) : null}
        {post.forwards > 0 ? (
          <span className="flex items-center gap-1.5">
            <ShareIcon size={13} />
            {compactNumber(post.forwards)}
          </span>
        ) : null}
        {post.is_deleted ? (
          <span style={{ color: "var(--destructive)" }}>deleted in Telegram</span>
        ) : null}
        <a
          href={post.url}
          target="_blank"
          rel="noreferrer"
          className="link-quiet ml-auto flex items-center gap-1.5"
        >
          Open in Telegram
          <ExternalIcon size={12} />
        </a>
      </div>

      {post.forward_from ? (
        <p className="mt-4 text-sm text-muted-foreground">
          forwarded from {post.forward_from.title ?? post.forward_from.username ?? "a channel"}
        </p>
      ) : null}

      {post.media.length > 0 ? (
        <div className="mt-5">
          <MediaGallery media={post.media} />
        </div>
      ) : null}

      {body ? (
        <div
          className="tg-body mt-5 whitespace-pre-wrap text-[1.125rem]"
          dangerouslySetInnerHTML={{ __html: body }}
        />
      ) : null}

      {post.poll ? (
        <div className="mt-5 max-w-md">
          <div className="font-medium">{post.poll.question}</div>
          <ul className="mt-3 space-y-2">
            {post.poll.answers.map((a, i) => {
              const total = post.poll?.total_voters || 0;
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
          {post.poll.total_voters ? (
            <p className="mt-2 text-xs text-muted-foreground">
              {compactNumber(post.poll.total_voters)} voted
            </p>
          ) : null}
        </div>
      ) : null}

      {reactions.length > 0 ? (
        <div className="mt-5 flex flex-wrap gap-1.5">
          {reactions.map((r, i) => (
            <span key={i} className="chip">
              <span aria-hidden>{r.emoji}</span>
              {compactNumber(r.count)}
            </span>
          ))}
        </div>
      ) : null}

      {post.links.length > 0 ? (
        <ul className="mt-6 space-y-2 border-t pt-4 text-sm">
          {post.links.map((l) => (
            <li key={l.url} className="flex items-baseline gap-3">
              <a
                href={l.url}
                target="_blank"
                rel="noreferrer nofollow"
                className="min-w-0 flex-1 truncate text-primary hover:underline"
              >
                {l.title ?? l.url}
              </a>
              <span className="shrink-0 text-xs text-muted-foreground">{l.domain}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

export { PostEntry };
