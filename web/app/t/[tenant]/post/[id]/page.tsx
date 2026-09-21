import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale } from "next-intl/server";
import { PostCard } from "@/components/post/PostCard";
import { TagChip } from "@/components/tags/TagChip";
import { apiFetchOrNull } from "@/lib/api";
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
    <div>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <PostCard post={post} full />
      {tags && tags.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <TagChip key={tag.slug} tag={tag} locale={locale} />
          ))}
        </div>
      ) : null}
      {related && related.items.length > 0 ? (
        <section className="mt-8">
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">Related</h2>
          <ul className="space-y-2 text-sm">
            {related.items.map((r) => (
              <li key={r.id}>
                <Link href={`/post/${r.id}`} className="hover:underline">
                  {r.title ?? r.text.slice(0, 90)}
                </Link>
                <span className="ml-2 text-xs text-muted-foreground">
                  {new Date(r.date).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <nav className="mt-6 flex justify-between text-sm">
        {post.prev_id ? <Link href={`/post/${post.prev_id}`}>← older</Link> : <span />}
        {post.next_id ? <Link href={`/post/${post.next_id}`}>newer →</Link> : <span />}
      </nav>
    </div>
  );
}
