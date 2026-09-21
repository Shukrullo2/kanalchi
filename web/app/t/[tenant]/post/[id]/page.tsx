import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PostCard } from "@/components/post/PostCard";
import { apiFetchOrNull } from "@/lib/api";
import type { PostOut, TenantPublic } from "@/lib/types";

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
  const [post, tenant] = await Promise.all([
    apiFetchOrNull<PostOut>(`/api/posts/${id}`),
    apiFetchOrNull<TenantPublic>("/api/tenant"),
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
      <nav className="mt-6 flex justify-between text-sm">
        {post.prev_id ? <Link href={`/post/${post.prev_id}`}>← older</Link> : <span />}
        {post.next_id ? <Link href={`/post/${post.next_id}`}>newer →</Link> : <span />}
      </nav>
    </div>
  );
}
