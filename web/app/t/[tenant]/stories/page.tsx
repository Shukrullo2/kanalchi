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
      <div className="py-16 text-center text-sm text-muted-foreground">
        Stories appear once the archive holds enough posts that follow one another.
      </div>
    );
  }

  return (
    <div>
      <header className="border-b pb-6">
        <h1 className="text-[1.75rem] font-semibold tracking-tight">Running stories</h1>
        <p className="mt-2 max-w-[60ch] text-[0.9375rem] text-muted-foreground">
          Posts that turned out to follow one another, grouped by what they are about and read back
          in the order the channel published them.
        </p>
      </header>
      <ul className="divide-y">
        {stories.map((s) => (
          <li key={s.slug}>
            <Link href={`/stories/${s.slug}`} className="block py-5">
              <h2 className="text-[1.0625rem] font-medium">{s.title[locale] ?? s.title.en}</h2>
              <p className="mt-1.5 max-w-[68ch] text-pretty text-[0.9375rem] text-muted-foreground">
                {s.summary[locale] ?? s.summary.en}
              </p>
              <p className="meta-row mt-2.5">
                <span>{s.post_count} posts</span>
                {s.first_at && s.last_at ? (
                  <span suppressHydrationWarning>
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
