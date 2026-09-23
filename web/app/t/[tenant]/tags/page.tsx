import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { apiFetch } from "@/lib/api";
import { byDimensionTier } from "@/lib/dimensions";
import type { DimensionOut } from "@/lib/types";

export async function generateMetadata() {
  const t = await getTranslations("tags");
  return { title: t("title") };
}

/**
 * The index has no "all groups" view — with seventeen of them and hundreds of
 * subjects each, one page would be a wall. It opens on the first subject group,
 * and the tabs carry you to the rest.
 */
export default async function TagsPage() {
  const [dimensions, t] = await Promise.all([
    apiFetch<DimensionOut[]>("/api/dimensions"),
    getTranslations("common"),
  ]);
  const first = byDimensionTier(dimensions)[0];
  if (!first) {
    return <p className="py-16 text-center text-sm text-muted-foreground">{t("notIndexedYet")}</p>;
  }
  redirect(`/tags/${first.key}`);
}
