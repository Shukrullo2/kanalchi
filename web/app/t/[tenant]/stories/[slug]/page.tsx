import Link from "@/components/AppLink";
import { notFound } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { ArrowLeftIcon } from "@/components/Icons";
import { apiFetchOrNull } from "@/lib/api";
import { postDate } from "@/lib/format";
import type { StoryDetail } from "@/lib/types";

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props) {
  const { slug } = await params;
  const [story, locale] = await Promise.all([
    apiFetchOrNull<StoryDetail>(`/api/stories/${slug}`),
    getLocale(),
  ]);
  return { title: story ? (story.title[locale] ?? story.title.en) : "Story" };
}

export default async function StoryPage({ params }: Props) {
  const { slug } = await params;
  const [story, locale, t, tc] = await Promise.all([
    apiFetchOrNull<StoryDetail>(`/api/stories/${slug}`),
    getLocale(),
    getTranslations("stories"),
    getTranslations("common"),
  ]);
  if (!story) notFound();

  return (
    <article>
      {/* Only reachable on a phone, where the list is the previous screen rather
          than the column beside this one. */}
      <Link href="/stories" className="stories-back link-quiet">
        <ArrowLeftIcon size={14} /> {t("all")}
      </Link>

      <header className="pb-6">
        <h1 className="text-balance text-[1.6rem] font-semibold tracking-tight sm:text-[1.9rem]">
          {story.title[locale] ?? story.title.en}
        </h1>
        <p className="mt-3 max-w-[68ch] text-pretty text-[0.9375rem] leading-relaxed text-muted-foreground">
          {story.summary[locale] ?? story.summary.en}
        </p>
        <p className="meta-row mt-3.5">
          <span>{tc("posts", { count: story.post_count })}</span>
          {story.first_at && story.last_at ? (
            <span suppressHydrationWarning>
              {postDate(story.first_at, locale)} – {postDate(story.last_at, locale)}
            </span>
          ) : null}
        </p>
      </header>

      {/* The story as the channel actually told it: one line per post, oldest
          first, so the shape of the coverage is visible before any one post is
          opened. */}
      <ol className="timeline">
        {story.items.map((p) => (
          <li key={p.id} className="timeline-item">
            <time className="timeline-date" dateTime={p.date} suppressHydrationWarning>
              {postDate(p.date, locale)}
            </time>
            <Link href={`/post/${p.id}`} className="timeline-title">
              {p.title ?? p.text.split("\n")[0].slice(0, 120)}
            </Link>
          </li>
        ))}
      </ol>
    </article>
  );
}
