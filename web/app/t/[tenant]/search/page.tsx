import { Suspense } from "react";
import { getLocale, getTranslations } from "next-intl/server";
import { SearchView, type SearchFilters } from "@/components/tags/SearchView";
import { apiFetch, apiFetchOrNull } from "@/lib/api";
import { dimensionLabel, tagLabel } from "@/lib/labels";
import type { DimensionOut, SearchResult, TagDetail, TenantPublic } from "@/lib/types";

export async function generateMetadata() {
  const t = await getTranslations("nav");
  return { title: t("search") };
}

type Params = { q?: string; tags?: string | string[]; sort?: string; period?: string; type?: string };
type Props = { searchParams: Promise<Params> };

const TYPES = ["none", "photo", "album", "video"] as const;
const DAY = 86_400_000;

/** `period` is "30d", "1y" or a four-digit year; anything else means no date filter. */
function periodRange(period: string | undefined): { from?: string; to?: string } {
  if (period === "30d") return { from: new Date(Date.now() - 30 * DAY).toISOString() };
  if (period === "1y") return { from: new Date(Date.now() - 365 * DAY).toISOString() };
  if (period && /^\d{4}$/.test(period)) return { from: `${period}-01-01T00:00:00Z`, to: `${period}-12-31T23:59:59Z` };
  return {};
}

export default async function SearchPage({ searchParams }: Props) {
  const sp = await searchParams;
  const tags = Array.isArray(sp.tags) ? sp.tags : sp.tags ? [sp.tags] : [];
  const type = (TYPES as readonly string[]).includes(sp.type ?? "") ? sp.type! : "";
  const range = periodRange(sp.period);
  const period = range.from ? (sp.period ?? "") : "";

  const qs = new URLSearchParams();
  if (sp.q) qs.set("q", sp.q);
  if (sp.sort) qs.set("sort", sp.sort);
  if (type) qs.set("media_kind", type);
  if (range.from) qs.set("date_from", range.from);
  if (range.to) qs.set("date_to", range.to);
  tags.forEach((t) => qs.append("tags", t));
  // The page asks for 20; "load more" asks the API directly with the same query and an offset.
  const query = qs.toString();

  const [results, dimensions, tenant, locale, t, common] = await Promise.all([
    apiFetch<SearchResult>(`/api/search?${query}&limit=20`),
    apiFetchOrNull<DimensionOut[]>("/api/dimensions"),
    apiFetchOrNull<TenantPublic>("/api/tenant"),
    getLocale(),
    getTranslations("search"),
    getTranslations("common"),
  ]);
  const groups = Object.fromEntries((dimensions ?? []).map((d) => [d.key, dimensionLabel(d, locale)]));
  // The filter chips come from the URL, which carries slugs. A slug is a Latin
  // transliteration, so a Russian reader would see "adliya-vazirligi" where the
  // rest of the page says "Министерство юстиции"; look each one up by name.
  const chosen = await Promise.all(tags.map((slug) => apiFetchOrNull<TagDetail>(`/api/tags/${slug}`)));
  const tagNames = Object.fromEntries(tags.map((slug, i) => [slug, chosen[i] ? tagLabel(chosen[i], locale) : slug]));

  // Years the archive covers, newest first, for the period filter.
  const first = tenant?.first_post_at ? new Date(tenant.first_post_at).getUTCFullYear() : null;
  const last = tenant?.last_post_at ? new Date(tenant.last_post_at).getUTCFullYear() : first;
  const years = first && last ? Array.from({ length: last - first + 1 }, (_, i) => last - i) : [];

  const filters: SearchFilters = { q: sp.q ?? "", tags, sort: sp.sort ?? "relevance", period, type };

  return (
    <Suspense>
      <SearchView
        initial={results}
        query={query}
        filters={filters}
        years={years}
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
          period: t("period"),
          periods: { "": t("anyTime"), "30d": t("days30"), "1y": t("year1") },
          type: t("type"),
          types: { "": t("anyType"), none: t("typeText"), photo: t("typePhoto"), album: t("typeAlbum"), video: t("typeVideo") },
          filters: t("filters"),
          results: t("results", { count: results.total ?? results.count }),
          resultsCapped: t("resultsCapped", { count: results.total ?? results.count }),
          moreTemplate: t.raw("more") as string,
          less: t("less"),
          loadMore: common("loadMore"),
        }}
      />
    </Suspense>
  );
}
