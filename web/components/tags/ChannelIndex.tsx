import Link from "next/link";
import { tierOf } from "@/lib/dimensions";
import { tagLabel } from "@/lib/labels";
import type { TagOut } from "@/lib/types";

type Tag = Pick<TagOut, "slug" | "name" | "labels" | "dimension" | "post_count">;

/**
 * What the channel writes about, and who it names — the two columns of a finding
 * aid.
 *
 * This is the archive's own index, which is the one thing the site has that
 * Telegram does not, so it opens the page. The bar sits behind the word at low
 * opacity rather than beside it: the list should read as a list of subjects,
 * with weight felt at a glance, not as a chart of tag counts.
 */
export function ChannelIndex({
  tags,
  locale,
  headings,
}: {
  tags: Tag[];
  locale: string;
  headings: { themes: string; entities: string; all: string };
}) {
  const themes = tags.filter((t) => tierOf(t.dimension) === "theme").slice(0, 7);
  const entities = tags.filter((t) => tierOf(t.dimension) === "entity").slice(0, 7);
  if (themes.length === 0 && entities.length === 0) return null;

  return (
    <section className="grid gap-x-10 gap-y-6 border-y py-6 sm:grid-cols-2">
      <IndexColumn title={headings.themes} tags={themes} locale={locale} />
      <IndexColumn title={headings.entities} tags={entities} locale={locale} />
      <Link href="/tags" className="link-quiet text-sm sm:col-span-2">
        {headings.all}
      </Link>
    </section>
  );
}

function IndexColumn({ title, tags, locale }: { title: string; tags: Tag[]; locale: string }) {
  if (tags.length === 0) return null;
  const max = Math.max(...tags.map((t) => t.post_count), 1);
  return (
    <div>
      <h2 className="mb-2 text-sm text-muted-foreground">{title}</h2>
      <ul className="-mx-1.5">
        {tags.map((tag) => (
          <li key={tag.slug}>
            <Link
              href={`/tag/${tag.slug}`}
              className="index-row"
              data-tier={tierOf(tag.dimension)}
              style={{ "--weight": `${Math.max(6, (tag.post_count / max) * 100)}%` } as React.CSSProperties}
            >
              <span className="index-name">{tagLabel(tag, locale)}</span>
              <span className="index-count">{tag.post_count}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
