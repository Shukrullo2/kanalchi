import Link from "@/components/AppLink";
import { useTranslations } from "next-intl";
import { EyeIcon } from "@/components/Icons";
import { TagRef } from "@/components/tags/TagChip";
import { byTier, tierOf } from "@/lib/dimensions";
import { compactNumber, fullDate, postDate } from "@/lib/format";
import type { PostOut } from "@/lib/types";

/**
 * One post in the archive grid.
 *
 * Most posts here are text, so the card leads with the opening line set large
 * and bold — that is what someone scans — and carries the rest as a snippet
 * underneath. Posts that have a picture show it, which gives a wall of cards
 * something to break the rhythm.
 */
export function PostEntry({
  post,
  locale,
  rank,
}: {
  post: PostOut;
  locale: string;
  /** Position in a ranked list, shown as a badge on the card. */
  rank?: number;
}) {
  // `useTranslations` reads from the server on a page and from the provider
  // inside `Timeline`, so one entry serves both trees.
  const t = useTranslations("post");
  const plain = stripTags(post.html ?? post.text);
  const { lead, rest } = split(plain);
  const thumb = post.media.find((m) => m.thumb_url || m.url);
  // Only the tags a reader scans by; language and media kind are filing details.
  const subjects = byTier(post.tags ?? [])
    .filter((t) => tierOf(t.dimension) !== "meta")
    .slice(0, 3);

  return (
    <article className="card-link">
      <div className="card h-full">
        {thumb ? (
          <Link href={`/post/${post.id}`} className="card-media block">
            {/* eslint-disable-next-line @next/next/no-img-element -- served from MinIO on this domain */}
            <img src={thumb.thumb_url ?? thumb.url ?? ""} alt="" loading="lazy" />
            {rank ? <span className="card-rank">{rank}</span> : null}
          </Link>
        ) : null}

        <div className="card-body">
          {!thumb && rank ? <span className="card-rank-inline">{rank}</span> : null}

          <Link href={`/post/${post.id}`} className="card-lead hover:underline">
            {lead || "…"}
          </Link>
          {rest ? <p className="card-snippet">{rest}</p> : null}

          {subjects.length > 0 ? (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              {subjects.map((tag) => (
                <TagRef key={tag.slug} tag={tag} locale={locale} />
              ))}
            </div>
          ) : null}

          <div className="card-foot">
            <time dateTime={post.date} title={fullDate(post.date, locale)} suppressHydrationWarning>
              {postDate(post.date, locale)}
            </time>
            {post.views > 0 ? (
              <span className="flex items-center gap-1.5">
                <EyeIcon size={13} />
                {compactNumber(post.views)}
              </span>
            ) : null}
            {post.media.length > 1 ? <span>{t("files", { count: post.media.length })}</span> : null}
            {post.poll ? <span>{t("poll")}</span> : null}
          </div>
        </div>
      </div>
    </article>
  );
}

function stripTags(html: string): string {
  return html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .trim();
}

/** First line as the headline, the remainder as the snippet. */
function split(text: string): { lead: string; rest: string } {
  const trimmed = text.replace(/\n{2,}/g, "\n").trim();
  if (!trimmed) return { lead: "", rest: "" };
  const breakAt = trimmed.search(/\n|(?<=[.!?…])\s/u);
  if (breakAt === -1 || breakAt > 140) {
    return { lead: trimmed.slice(0, 140), rest: trimmed.slice(140, 400).trim() };
  }
  return { lead: trimmed.slice(0, breakAt).trim(), rest: trimmed.slice(breakAt, breakAt + 400).trim() };
}
