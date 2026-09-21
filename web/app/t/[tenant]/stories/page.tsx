import Link from "next/link";
import { getLocale } from "next-intl/server";
import { apiFetch } from "@/lib/api";
import { postDate } from "@/lib/format";
import type { StoryOut } from "@/lib/types";

export const metadata = { title: "Stories" };

export default async function StoriesPage() {
  const [stories, locale] = await Promise.all([apiFetch<StoryOut[]>("/api/stories"), getLocale()]);

  if (stories.length === 0) {
    return (
      <div className="card-surface p-12 text-center text-sm text-muted-foreground">
        Stories appear once enough related posts have accumulated.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Stories</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Posts that belong to one running story, grouped by what they are about.
        </p>
      </header>
      <ul className="space-y-3">
        {stories.map((s, i) => (
          <li key={s.slug} className="animate-rise" style={{ animationDelay: `${Math.min(i, 8) * 30}ms` }}>
            <Link href={`/stories/${s.slug}`} className="card-surface card-hover block p-4">
              <h2 className="font-medium">{s.title[locale] ?? s.title.en}</h2>
              <p className="mt-1 text-pretty text-sm text-muted-foreground">
                {s.summary[locale] ?? s.summary.en}
              </p>
              <p className="meta-row mt-2.5">
                <span>{s.post_count} posts</span>
                {s.first_at && s.last_at ? (
                  <span className="divider-dot">
                    {postDate(s.first_at, locale)} – {postDate(s.last_at, locale)}
                  </span>
                ) : null}
              </p>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
