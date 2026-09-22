"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { SearchIcon } from "@/components/Icons";

/**
 * Search and sort, sitting above the archive.
 *
 * Search is the fastest way into twelve thousand posts, so it is the first
 * control on the page rather than a link in the navigation. Typing here jumps to
 * the search page, which owns the filtering.
 */
export function ArchiveControls({
  placeholder,
  sorts,
  totalLabel,
}: {
  placeholder: string;
  sorts: { href: string; label: string; active?: boolean }[];
  /** Already formatted, e.g. "12 948 ta post". */
  totalLabel: string;
}) {
  const router = useRouter();
  const [q, setQ] = useState("");

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <form
        className="search-field sm:max-w-sm"
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim()) router.push(`/search?q=${encodeURIComponent(q.trim())}`);
        }}
      >
        <SearchIcon size={16} className="shrink-0 text-muted-foreground" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={placeholder}
          aria-label={placeholder}
        />
      </form>

      <div className="no-scrollbar flex gap-2 overflow-x-auto">
        {sorts.map((s) => (
          <a key={s.href} href={s.href} className="pill" data-active={s.active}>
            {s.label}
          </a>
        ))}
      </div>

      <span className="tnum shrink-0 text-sm text-muted-foreground sm:ml-auto">{totalLabel}</span>
    </div>
  );
}
