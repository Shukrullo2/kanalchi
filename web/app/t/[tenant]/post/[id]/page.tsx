import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale } from "next-intl/server";
import { ArrowLeftIcon, ArrowRightIcon } from "@/components/Icons";
import { PostCard } from "@/components/post/PostCard";
import { TagChip } from "@/components/tags/TagChip";
import { byTier, tierOf } from "@/lib/dimensions";
import { apiFetchOrNull } from "@/lib/api";
import { postDate } from "@/lib/format";
import type { PostOut, TagOut, TenantPublic } from "@/lib/types";

type Props = { params: Promise<{ id: string }> };

function plain(html: string | null, text: string) {
  return (html ? html.replace(/<[^>]+>/g, " ") : text).replace(/\s+/g, " ").trim();
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const [post, tenant] = await Promise.all([
    apiFetchOrNull<PostOut>(`/api/posts/${id}`),
    apiFetchOrNull<TenantPublic>("/api/tenant"),
  ]);
  if (!post) return { title: "Not found" };
  const description = post.summary ?? plain(post.html, post.text).slice(0, 200);
  const image = post.media.find((m) => m.thumb_url || m.url)?.thumb_url ?? undefined;
  return {
    title: post.title ?? `${description.slice(0, 60)} · ${tenant?.title ?? ""}`,
    description,
    openGraph: {
      title: post.title ?? tenant?.title ?? "",
      description,
      type: "article",
      publishedTime: post.date,
      images: image ? [image] : undefined,
    },
  };
}

export default async function PostPage({ params }: Props) {
  const { id } = await params;
  const [post, tenant, tags, related, locale] = await Promise.all([
    apiFetchOrNull<PostOut>(`/api/posts/${id}`),
    apiFetchOrNull<TenantPublic>("/api/tenant"),
    apiFetchOrNull<TagOut[]>(`/api/posts/${id}/tags`),
    apiFetchOrNull<{ items: PostOut[] }>(`/api/posts/${id}/related?limit=4`),
    getLocale(),
  ]);
  if (!post) notFound();

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    headline: post.title ?? plain(post.html, post.text).slice(0, 110),
    datePublished: post.date,
    dateModified: post.edit_date ?? post.date,
    author: { "@type": "Organization", name: tenant?.title ?? "" },
    mainEntityOfPage: `https://${tenant?.domain ?? ""}/post/${post.id}`,
  };

  const subjects = tags ? byTier(tags).filter((t) => tierOf(t.dimension) !== "meta") : [];
  const filing = tags ? tags.filter((t) => tierOf(t.dimension) === "meta") : [];

  return (
    <div>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />

      <PostCard post={post} locale={locale} full />

      {subjects.length > 0 ? (
        <section className="mt-8 border-t pt-4">
          <h2 className="mb-2.5 text-sm text-muted-foreground">Indexed under</h2>
          <div className="flex flex-wrap gap-1.5">
            {subjects.map((tag) => (
              <TagChip key={tag.slug} tag={tag} locale={locale} />
            ))}
          </div>
          {filing.length > 0 ? (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {filing.map((tag) => (
                <TagChip key={tag.slug} tag={tag} locale={locale} />
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      {related && related.items.length > 0 ? (
        <section className="mt-8 border-t pt-4">
          <h2 className="mb-2.5 text-sm text-muted-foreground">Close to this in the archive</h2>
          <ul className="space-y-0.5">
            {related.items.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/post/${r.id}`}
                  className="flex items-baseline justify-between gap-4 rounded py-1.5 text-sm hover:text-primary"
                >
                  <span className="min-w-0 flex-1 truncate">
                    {r.title ?? plain(r.html, r.text).slice(0, 90)}
                  </span>
                  <span className="tnum shrink-0 text-xs text-muted-foreground" suppressHydrationWarning>
                    {postDate(r.date, locale)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <nav className="mt-10 flex justify-between gap-3 border-t pt-5 text-sm">
        {post.prev_id ? (
          <Link href={`/post/${post.prev_id}`} className="link-quiet flex items-center gap-1.5">
            <ArrowLeftIcon size={14} /> Earlier post
          </Link>
        ) : (
          <span />
        )}
        {post.next_id ? (
          <Link href={`/post/${post.next_id}`} className="link-quiet flex items-center gap-1.5">
            Later post <ArrowRightIcon size={14} />
          </Link>
        ) : (
          <span />
        )}
      </nav>
    </div>
  );
}
