import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale } from "next-intl/server";
import { ArrowLeftIcon } from "@/components/Icons";
import { apiFetch } from "@/lib/api";
import { dimensionLabel, tagLabel } from "@/lib/labels";
import type { DimensionOut, TagOut } from "@/lib/types";
import { toneVar } from "@/lib/dimensions";

type Props = { params: Promise<{ dimension: string }> };

export default async function DimensionPage({ params }: Props) {
  const { dimension } = await params;
  const [dimensions, tags, locale] = await Promise.all([
    apiFetch<DimensionOut[]>("/api/dimensions"),
    apiFetch<TagOut[]>(`/api/tags?dimension=${encodeURIComponent(dimension)}&limit=500`),
    getLocale(),
  ]);
  const dim = dimensions.find((d) => d.key === dimension);
  if (!dim) notFound();
  const max = Math.max(1, ...tags.map((t) => t.post_count));

  return (
    <div className="space-y-5">
      <header className="flex items-baseline gap-2">
        <span
          className="inline-block h-2.5 w-2.5 rounded-full"
          style={{ background: toneVar(dim.key) }}
          aria-hidden
        />
        <h1 className="text-xl font-semibold tracking-tight">{dimensionLabel(dim, locale)}</h1>
        <span className="text-sm text-muted-foreground">{tags.length}</span>
      </header>
      {dim.description ? <p className="text-sm text-muted-foreground">{dim.description}</p> : null}

      <ul className="card-surface divide-y overflow-hidden">
        {tags.map((tag) => (
          <li key={tag.slug}>
            <Link href={`/tag/${tag.slug}`} className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-surface-2">
              <span className="min-w-0 flex-1 truncate">{tagLabel(tag, locale)}</span>
              <span className="hidden h-1 w-24 overflow-hidden rounded-full bg-border sm:block">
                <span
                  className="block h-full rounded-full"
                  style={{
                    width: `${(tag.post_count / max) * 100}%`,
                    background: toneVar(dim.key),
                  }}
                />
              </span>
              <span className="w-10 shrink-0 text-right text-sm tabular-nums text-muted-foreground">
                {tag.post_count}
              </span>
            </Link>
          </li>
        ))}
      </ul>

      <Link href="/tags" className="link-quiet inline-flex items-center gap-1.5 text-sm">
        <ArrowLeftIcon size={14} /> all tags
      </Link>
    </div>
  );
}
