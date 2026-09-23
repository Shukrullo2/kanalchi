import { Suspense } from "react";
import { getLocale, getTranslations } from "next-intl/server";
import { SearchView } from "@/components/tags/SearchView";
import { apiFetch, apiFetchOrNull } from "@/lib/api";
import { dimensionLabel } from "@/lib/labels";
import { tagLabel } from "@/lib/labels";
import type { DimensionOut, SearchResult, TagDetail } from "@/lib/types";

export async function generateMetadata() {
  const t = await getTranslations("nav");
  return { title: t("search") };
}

type Props = { searchParams: Promise<{ q?: string; tags?: string | string[]; sort?: string }> };

export default async function SearchPage({ searchParams }: Props) {
  const sp = await searchParams;
  const tags = Array.isArray(sp.tags) ? sp.tags : sp.tags ? [sp.tags] : [];
  const qs = new URLSearchParams();
  if (sp.q) qs.set("q", sp.q);
  if (sp.sort) qs.set("sort", sp.sort);
  tags.forEach((t) => qs.append("tags", t));
  qs.set("limit", "20");

  const [results, dimensions, locale, t] = await Promise.all([
    apiFetch<SearchResult>(`/api/search?${qs.toString()}`),
    apiFetchOrNull<DimensionOut[]>("/api/dimensions"),
    getLocale(),
    getTranslations("search"),
  ]);
  const groups = Object.fromEntries(
    (dimensions ?? []).map((d) => [d.key, dimensionLabel(d, locale)]),
  );
  // The filter chips come from the URL, which carries slugs. A slug is a Latin
  // transliteration, so a Russian reader would see "adliya-vazirligi" where the
  // rest of the page says "Министерство юстиции"; look each one up by name.
  const chosen = await Promise.all(tags.map((t) => apiFetchOrNull<TagDetail>(`/api/tags/${t}`)));
  const tagNames = Object.fromEntries(
    tags.map((slug, i) => [slug, chosen[i] ? tagLabel(chosen[i], locale) : slug]),
  );

  return (
    <Suspense>
      <SearchView
        initial={results}
        locale={locale}
        groups={groups}
        tagNames={tagNames}
        labels={{
          search: t("placeholder"),
          nothing: t("nothing"),
          sortBy: t("sortBy"),
          clear: t("clear"),
          sorts: {
            relevance: t("relevance"),
            newest: t("newest"),
            oldest: t("oldest"),
            views: t("views"),
            reactions: t("reactions"),
          },
        }}
      />
    </Suspense>
  );
}
