import Link from "next/link";
import type { TagOut } from "@/lib/types";
import { tagLabel } from "@/lib/labels";

export function TagChip({ tag, locale, showCount = false }: { tag: TagOut; locale: string; showCount?: boolean }) {
  return (
    <Link
      href={`/tag/${tag.slug}`}
      className="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs hover:bg-muted"
    >
      {tagLabel(tag, locale)}
      {showCount ? <span className="text-muted-foreground">{tag.post_count}</span> : null}
    </Link>
  );
}
