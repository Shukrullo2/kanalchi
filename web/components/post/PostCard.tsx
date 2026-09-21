import Link from "next/link";
import type { PostOut } from "@/lib/types";
import { MediaGallery } from "./MediaGallery";
import { PostMeta } from "./PostMeta";

/** `locale` is passed in rather than read from context so this renders from both server and client
 *  components, and so dates format once with the full ICU data available on the server. */
export function PostCard({ post, locale, full = false }: { post: PostOut; locale: string; full?: boolean }) {
  const body = post.html ?? post.text;
  return (
    <article className={`card-surface p-4 sm:p-5 ${full ? "" : "card-hover"}`}>
      {post.forward_from ? (
        <p className="mb-2.5 flex items-center gap-1.5 text-xs text-muted-foreground">
          <span aria-hidden>↪</span>
          {post.forward_from.title ?? post.forward_from.username ?? "forwarded"}
        </p>
      ) : null}

      {post.media.length > 0 ? (
        <div className="mb-3.5">
          <MediaGallery media={post.media} />
        </div>
      ) : null}

      {body ? <div className="tg-body whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: body }} /> : null}

      {post.truncated ? (
        <Link href={`/post/${post.id}`} className="mt-1.5 inline-block text-sm text-primary hover:underline">
          Read more
        </Link>
      ) : null}

      {post.poll ? (
        <div className="mt-3.5 rounded-lg border bg-surface-2 p-3.5">
          <div className="text-sm font-medium">{post.poll.question}</div>
          <ul className="mt-2.5 space-y-1.5">
            {post.poll.answers.map((a, i) => {
              const total = post.poll?.total_voters || 0;
              const share = total ? Math.round(((a.voters ?? 0) / total) * 100) : 0;
              return (
                <li key={i} className="text-sm">
                  <div className="flex justify-between gap-4 text-muted-foreground">
                    <span>{a.text}</span>
                    <span className="tabular-nums">{share}%</span>
                  </div>
                  <div className="mt-1 h-1 overflow-hidden rounded-full bg-border">
                    <div className="h-full rounded-full bg-primary/70" style={{ width: `${share}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {full && post.links.length > 0 ? (
        <ul className="mt-4 space-y-1.5 border-t pt-3.5 text-sm">
          {post.links.map((l) => (
            <li key={l.url} className="flex items-baseline gap-2">
              <a href={l.url} target="_blank" rel="noreferrer nofollow" className="truncate text-primary hover:underline">
                {l.title ?? l.url}
              </a>
              <span className="shrink-0 text-xs text-muted-foreground">{l.domain}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <PostMeta post={post} locale={locale} />
    </article>
  );
}
