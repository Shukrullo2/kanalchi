/**
 * Which of the three tiers a dimension belongs to.
 *
 * A reader scanning a post's tags separates three things and no more: what the
 * post is about, who or what it names, and how it was filed. Giving every
 * dimension its own hue made a row of eight tags read as confetti; giving them
 * three makes the row read. The dimension itself is still visible — it is the
 * grouping on the index pages and the label on the tag page.
 */
export type Tier = "theme" | "entity" | "meta";

const ENTITY = new Set([
  "people",
  "gov_orgs",
  "orgs",
  "locations",
  "products",
  "events",
  "laws",
  "media_outlets",
  "mentions",
  "tg_channels",
]);

const META = new Set([
  "link_domains",
  "hashtags",
  "format",
  "stance",
  "language",
  "media_type",
  "dates",
]);

export function tierOf(dimension?: string | null): Tier {
  if (!dimension) return "meta";
  if (ENTITY.has(dimension)) return "entity";
  if (META.has(dimension)) return "meta";
  // `themes` and the channel-specific dimensions discovered during indexing are
  // topical, so they take the subject tone.
  return "theme";
}

/** Tags in a post row read best grouped: subject first, then names, then filing. */
export function byTier<T extends { dimension?: string | null }>(tags: T[]): T[] {
  const order: Record<Tier, number> = { theme: 0, entity: 1, meta: 2 };
  return [...tags].sort((a, b) => order[tierOf(a.dimension)] - order[tierOf(b.dimension)]);
}

/** The colour a dimension paints with, for inline styles: gold for subjects, sky for names. */
export function toneVar(dimension?: string | null): string {
  const tier = tierOf(dimension);
  if (tier === "theme") return "var(--primary)";
  if (tier === "entity") return "var(--accent)";
  return "var(--muted-foreground)";
}

/**
 * Groups in the order a reader wants them: what posts are about, then who and
 * what they name, then how they were filed. Left alone, the biggest group wins
 * the front page — and that is `link_domains`, a thousand hostnames, which is
 * the least interesting thing the index knows.
 */
export function byDimensionTier<T extends { key: string; tag_count: number }>(dimensions: T[]): T[] {
  const rank: Record<Tier, number> = { theme: 0, entity: 1, meta: 2 };
  return [...dimensions].sort(
    (a, b) => rank[tierOf(a.key)] - rank[tierOf(b.key)] || b.tag_count - a.tag_count,
  );
}
