import type { DimensionOut, TagOut } from "./types";

/** Localised label with a sensible fallback chain: locale -> en -> canonical name. */
export function tagLabel(tag: Pick<TagOut, "labels" | "name">, locale: string): string {
  return tag.labels?.[locale] || tag.labels?.en || tag.name;
}

export function dimensionLabel(dim: Pick<DimensionOut, "labels" | "key">, locale: string): string {
  return dim.labels?.[locale] || dim.labels?.en || dim.key;
}
