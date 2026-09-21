import Link from "next/link";
import type { PostOut } from "@/lib/types";
import { MediaGallery } from "./MediaGallery";
import { PostMeta } from "./PostMeta";

export function PostCard({ post, full = false }: { post: PostOut; full?: boolean }) {
  const body = post.html ?? post.text;
  return (
    <article className="border-b py-6 last:border-b-0">
      {post.forward_from ? (
        <p className="mb-2 text-xs text-muted-foreground">
          ↪ {post.forward_from.title ?? post.forward_from.username ?? "forwarded"}
        </p>
      ) : null}
      {post.media.length > 0 ? <MediaGallery media={post.media} /> : null}
      {body ? (
        <div className="tg-body prose-sm mt-3 whitespace-pre-wrap break-words" dangerouslySetInnerHTML={{ __html: body }} />
      ) : null}
      {post.truncated ? (
        <Link href={`/post/${post.id}`} className="mt-1 inline-block text-sm underline">
          …
        </Link>
      ) : null}
      {post.poll ? (
        <div className="mt-3 rounded-lg border p-3 text-sm">
          <div className="font-medium">{post.poll.question}</div>
          <ul className="mt-2 space-y-1">
            {post.poll.answers.map((a, i) => (
              <li key={i} className="flex justify-between gap-4 text-muted-foreground">
                <span>{a.text}</span>
                <span>{a.voters ?? 0}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {full && post.links.length > 0 ? (
        <ul className="mt-3 space-y-1 text-sm">
          {post.links.map((l) => (
            <li key={l.url}>
              <a href={l.url} target="_blank" rel="noreferrer nofollow" className="underline">
                {l.title ?? l.url}
              </a>
              <span className="ml-2 text-xs text-muted-foreground">{l.domain}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <PostMeta post={post} />
    </article>
  );
}
