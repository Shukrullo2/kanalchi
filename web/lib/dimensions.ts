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

/**
 * A colour of its own for each group's cloud.
 *
 * The three tiers exist because a row of eight tags under a post, each in its
 * own hue, reads as confetti. A cloud is not that row: it is one group, alone
 * on the page, so a hue per group costs nothing and tells you at a glance that
 * the tab you just pressed took you somewhere else.
 *
 * What comes back is a tint, not a colour. The stylesheet mixes a quarter of it
 * into the tier's own tone, so every cloud stays recognisably gold, sky or grey
 * — and stays whatever those tokens mean in the current theme — while no two
 * groups land on quite the same shade. The hue is hashed from the key, so a
 * group keeps its colour forever and dimensions discovered during indexing get
 * one without anybody choosing it.
 */
export function dimensionTint(key: string): string {
  let h = 2166136261;
  for (let i = 0; i < key.length; i += 1) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const n = h >>> 0;
  // Saturation and lightness vary as well as hue, because hue alone is not
  // enough: across two dozen groups and 360 degrees a clash is more likely than
  // not, and `custom_banks` and `custom_data_sources` did in fact land on the
  // same one. Three varying channels make a visible collision improbable.
  return `hsl(${n % 360} ${58 + ((n >>> 9) % 26)}% ${50 + ((n >>> 18) % 15)}%)`;
}
