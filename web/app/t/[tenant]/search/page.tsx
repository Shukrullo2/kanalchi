import { Suspense } from "react";
import { getLocale, getTranslations } from "next-intl/server";
import { SearchView } from "@/components/tags/SearchView";
import { apiFetch } from "@/lib/api";
import type { SearchResult } from "@/lib/types";

export const metadata = { title: "Search" };

type Props = { searchParams: Promise<{ q?: string; tags?: string | string[]; sort?: string }> };

export default async function SearchPage({ searchParams }: Props) {
  const sp = await searchParams;
  const tags = Array.isArray(sp.tags) ? sp.tags : sp.tags ? [sp.tags] : [];
  const qs = new URLSearchParams();
  if (sp.q) qs.set("q", sp.q);
  if (sp.sort) qs.set("sort", sp.sort);
  tags.forEach((t) => qs.append("tags", t));
  qs.set("limit", "20");

  const [results, locale, t] = await Promise.all([
    apiFetch<SearchResult>(`/api/search?${qs.toString()}`),
    getLocale(),
    getTranslations("search"),
  ]);

  return (
    <Suspense>
      <SearchView
        initial={results}
        locale={locale}
        labels={{ search: t("placeholder"), nothing: t("nothing"), sortBy: t("sortBy"), clear: t("clear") }}
      />
    </Suspense>
  );
}
