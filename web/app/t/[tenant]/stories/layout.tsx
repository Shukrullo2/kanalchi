import { getLocale, getTranslations } from "next-intl/server";
import { StoriesShell } from "@/components/stories/StoriesShell";
import { apiFetch } from "@/lib/api";
import type { StoryOut } from "@/lib/types";

/**
 * Fetched once for the whole section: the list down the left is the same on the
 * index and on every story, so putting it in the layout keeps it from being
 * re-requested and re-rendered each time you pick a different one.
 */
export default async function StoriesLayout({ children }: { children: React.ReactNode }) {
  const [stories, locale, t] = await Promise.all([
    apiFetch<StoryOut[]>("/api/stories"),
    getLocale(),
    getTranslations("stories"),
  ]);

  if (stories.length === 0) {
    return <div className="py-16 text-center text-sm text-muted-foreground">{t("empty")}</div>;
  }

  return (
    <StoriesShell stories={stories} locale={locale} heading={t("title")}>
      {children}
    </StoriesShell>
  );
}
