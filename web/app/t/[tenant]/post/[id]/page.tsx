import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale } from "next-intl/server";
import { ArrowLeftIcon, ArrowRightIcon } from "@/components/Icons";
import { PostCard } from "@/components/post/PostCard";
import { TagChip } from "@/components/tags/TagChip";
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

  return (
    <div className="space-y-5">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />

      <PostCard post={post} locale={locale} full />

      {tags && tags.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <TagChip key={tag.slug} tag={tag} locale={locale} />
          ))}
        </div>
      ) : null}

      {related && related.items.length > 0 ? (
        <section className="card-surface p-4 sm:p-5">
          <h2 className="mb-3 text-sm font-medium">Related posts</h2>
          <ul className="space-y-2.5">
            {related.items.map((r) => (
              <li key={r.id} className="flex items-baseline justify-between gap-3 text-sm">
                <Link href={`/post/${r.id}`} className="min-w-0 flex-1 truncate hover:text-primary">
                  {r.title ?? plain(r.html, r.text).slice(0, 90)}
                </Link>
                <span className="shrink-0 text-xs text-muted-foreground">{postDate(r.date, locale)}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <nav className="flex justify-between gap-3 text-sm">
        {post.prev_id ? (
          <Link href={`/post/${post.prev_id}`} className="btn-ghost">
            <ArrowLeftIcon size={14} /> older
          </Link>
        ) : (
          <span />
        )}
        {post.next_id ? (
          <Link href={`/post/${post.next_id}`} className="btn-ghost">
            newer <ArrowRightIcon size={14} />
          </Link>
        ) : (
          <span />
        )}
      </nav>
    </div>
  );
}
