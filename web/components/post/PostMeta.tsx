import Link from "@/components/AppLink";
import { getTranslations } from "next-intl/server";
import { ExternalIcon, EyeIcon, ShareIcon } from "@/components/Icons";
import { compactNumber, fullDate, postDate } from "@/lib/format";
import type { PostOut } from "@/lib/types";

/** Server component on purpose: dates are formatted once, on the server, where full ICU data lives. */
export async function PostMeta({ post, locale }: { post: PostOut; locale: string }) {
  const t = await getTranslations("post");
  const reactions = post.reactions.filter((r) => r.emoji).slice(0, 4);
  return (
    <div className="meta-row mt-3">
      <Link href={`/post/${post.id}`} className="link-quiet" title={fullDate(post.date, locale)}>
        <time dateTime={post.date} suppressHydrationWarning>
          {postDate(post.date, locale)}
        </time>
      </Link>

      {post.views > 0 ? (
        <span className="flex items-center gap-1">
          <EyeIcon size={13} />
          {compactNumber(post.views)}
        </span>
      ) : null}

      {post.forwards > 0 ? (
        <span className="flex items-center gap-1">
          <ShareIcon size={13} />
          {compactNumber(post.forwards)}
        </span>
      ) : null}

      {reactions.length > 0 ? (
        <span className="flex items-center gap-1">
          {reactions.map((r, i) => (
            <span key={i} className="chip">
              <span aria-hidden>{r.emoji}</span>
              {compactNumber(r.count)}
            </span>
          ))}
        </span>
      ) : null}

      {post.is_deleted ? (
        <span className="chip" style={{ color: "var(--destructive)" }}>
          {t("deleted")}
        </span>
      ) : null}

      <a href={post.url} target="_blank" rel="noreferrer" className="link-quiet ml-auto flex items-center gap-1">
        {t("telegram")}
        <ExternalIcon size={12} />
      </a>
    </div>
  );
}
