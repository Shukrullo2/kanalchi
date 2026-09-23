import { getLocale, getTranslations } from "next-intl/server";
import { GraphView } from "@/components/graph/GraphView";
import { apiFetch, apiFetchOrNull } from "@/lib/api";
import { isoDay } from "@/lib/graph";
import { dimensionLabel } from "@/lib/labels";
import type { DimensionOut, GraphOut } from "@/lib/types";

type Params = Record<string, string | string[] | undefined>;
type Props = { searchParams: Promise<Params> };

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const MS_DAY = 86_400_000;
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

/** "The last N days" ending today, dated here so the client never needs a clock. */
function lastDays(days: number): [string, string] {
  const to = Date.now();
  return [isoDay(to - days * MS_DAY), isoDay(to)];
}

export async function generateMetadata() {
  const t = await getTranslations("graph");
  return { title: t("title") };
}

/**
 * The archive as a map. The date window comes from the URL and decides what
 * the server sends; the rest of the URL (search, picked subjects, hidden
 * groups, which map) is read once here and then kept by the client.
 *
 * There is no page chrome: the canvas takes the whole viewport and the
 * controls float over it, the way a graph view does in Obsidian.
 */
export default async function GraphPage({ searchParams }: Props) {
  const sp = await searchParams;
  const qs = new URLSearchParams();
  const days = Number(one(sp.days));
  if (days > 0 && days <= 3650) {
    const [from, to] = lastDays(days);
    qs.set("from", from);
    qs.set("to", to);
  } else {
    const from = one(sp.from);
    const to = one(sp.to);
    if (from && DAY.test(from)) qs.set("from", from);
    if (to && DAY.test(to)) qs.set("to", to);
  }

  const [data, dimensions, locale, t] = await Promise.all([
    apiFetch<GraphOut>(`/api/graph?${qs}`),
    apiFetchOrNull<DimensionOut[]>("/api/dimensions"),
    getLocale(),
    getTranslations("graph"),
  ]);
  const dimensionLabels = Object.fromEntries((dimensions ?? []).map((d) => [d.key, dimensionLabel(d, locale)]));
  const list = (v: string | undefined) => (v ?? "").split(",").filter(Boolean);

  return (
    <div>
      <h1 className="sr-only">{t("title")}</h1>
      <GraphView
        data={data}
        locale={locale}
        dimensionLabels={dimensionLabels}
        initial={{
          mode: one(sp.mode) === "posts" ? "constellation" : "tags",
          tags: list(one(sp.tags)),
          off: list(one(sp.off)),
          q: one(sp.q) ?? "",
        }}
      />
    </div>
  );
}
