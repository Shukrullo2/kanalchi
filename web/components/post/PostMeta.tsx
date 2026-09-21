import Link from "next/link";
import type { PostOut } from "@/lib/types";

function compact(n: number) {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function PostMeta({ post }: { post: PostOut }) {
  const date = new Date(post.date);
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      <Link href={`/post/${post.id}`} className="hover:text-foreground">
        <time dateTime={post.date}>{date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</time>
      </Link>
      {post.views > 0 ? <span>{compact(post.views)} 👁</span> : null}
      {post.reactions_total > 0 ? (
        <span className="flex gap-1">
          {post.reactions
            .filter((r) => r.emoji)
            .slice(0, 5)
            .map((r, i) => (
              <span key={i}>
                {r.emoji} {r.count}
              </span>
            ))}
        </span>
      ) : null}
      {post.forwards > 0 ? <span>↗ {compact(post.forwards)}</span> : null}
      {post.is_deleted ? <span className="rounded bg-red-100 px-1 text-red-700">deleted in Telegram</span> : null}
      <a href={post.url} target="_blank" rel="noreferrer" className="ml-auto hover:text-foreground">
        Telegram ↗
      </a>
    </div>
  );
}
