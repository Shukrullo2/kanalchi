import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale } from "next-intl/server";
import { ArrowLeftIcon } from "@/components/Icons";
import { PostCard } from "@/components/post/PostCard";
import { apiFetchOrNull } from "@/lib/api";
import { postDate } from "@/lib/format";
import type { StoryDetail } from "@/lib/types";

type Props = { params: Promise<{ slug: string }> };

export default async function StoryPage({ params }: Props) {
  const { slug } = await params;
  const [story, locale] = await Promise.all([
    apiFetchOrNull<StoryDetail>(`/api/stories/${slug}`),
    getLocale(),
  ]);
  if (!story) notFound();

  return (
    <div className="space-y-5">
      <header className="card-surface space-y-2 p-4 sm:p-5">
        <h1 className="text-balance text-xl font-semibold tracking-tight">
          {story.title[locale] ?? story.title.en}
        </h1>
        <p className="text-pretty text-sm text-muted-foreground">{story.summary[locale] ?? story.summary.en}</p>
        <p className="meta-row">
          <span>{story.post_count} posts</span>
          {story.first_at && story.last_at ? (
            <span className="divider-dot">
              {postDate(story.first_at, locale)} – {postDate(story.last_at, locale)}
            </span>
          ) : null}
        </p>
      </header>

      <ol className="space-y-3.5">
        {story.items.map((p) => (
          <li key={p.id}>
            <PostCard post={p} locale={locale} />
          </li>
        ))}
      </ol>

      <Link href="/stories" className="link-quiet inline-flex items-center gap-1.5 text-sm">
        <ArrowLeftIcon size={14} /> all stories
      </Link>
    </div>
  );
}
