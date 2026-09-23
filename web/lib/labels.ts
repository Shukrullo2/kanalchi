import type { DimensionOut, TagOut } from "./types";

/** Localised label with a sensible fallback chain: locale -> en -> canonical name. */
export function tagLabel(tag: Pick<TagOut, "labels" | "name">, locale: string): string {
  return tag.labels?.[locale] || tag.labels?.en || tag.name;
}

export function dimensionLabel(dim: Pick<DimensionOut, "labels" | "key">, locale: string): string {
  return dim.labels?.[locale] || dim.labels?.en || dim.key;
}

/**
 * The sentence under a name, in the reader's language — and only in it.
 *
 * Labels fall back to English because a name has to be printed somehow. A
 * description does not: the page reads perfectly well without one, and an
 * English sentence under an Uzbek heading is worse than a heading on its own.
 * So a tag or group indexed before its Uzbek and Russian lines were written
 * simply shows no line until the next rebuild fills them in.
 */
export function localeText(
  texts: Record<string, string> | null | undefined,
  locale: string,
): string | null {
  return texts?.[locale]?.trim() || null;
}

export function tagDescription(tag: Pick<TagOut, "descriptions">, locale: string): string | null {
  return localeText(tag.descriptions, locale);
}

export function dimensionDescription(
  dim: Pick<DimensionOut, "descriptions">,
  locale: string,
): string | null {
  return localeText(dim.descriptions, locale);
}
