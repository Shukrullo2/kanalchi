import { getLocale } from "next-intl/server";
import { TagManager } from "@/components/studio/TagManager";
import { apiFetch } from "@/lib/api";
import type { PendingTag, TagOut } from "@/lib/types";

export default async function StudioTagsPage() {
  const [pending, tags, locale] = await Promise.all([
    apiFetch<PendingTag[]>("/api/studio/tags/pending"),
    apiFetch<TagOut[]>("/api/tags?limit=300"),
    getLocale(),
  ]);
  return <TagManager pending={pending} tags={tags} locale={locale} />;
}
