"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { StoryOut } from "@/lib/types";

/**
 * The stories section: every story's title down the left, the one you picked on
 * the right.
 *
 * The list is the same on every story, so it lives in the layout and survives
 * navigation between them — you read one story, glance left, and take the next
 * without going back to an index first.
 *
 * On a phone there is no room for both, so the two halves become two screens:
 * the list is what `/stories` shows, and picking one replaces it with the
 * story. The stylesheet does that switch off `data-detail`, which is why this
 * needs the pathname and therefore the client.
 */
export function StoriesShell({
  stories,
  locale,
  heading,
  children,
}: {
  stories: StoryOut[];
  locale: string;
  /** Shown above the list only where the list is the whole screen. */
  heading: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const active = pathname.match(/\/stories\/([^/?#]+)/)?.[1];

  return (
    <div className="stories-shell" data-detail={Boolean(active)}>
      <nav className="stories-side" aria-label="Stories">
        <h2 className="stories-side-heading">{heading}</h2>
        <ol>
          {stories.map((s) => (
            <li key={s.slug}>
              <Link
                href={`/stories/${s.slug}`}
                className="stories-side-item"
                data-active={s.slug === active}
                aria-current={s.slug === active ? "page" : undefined}
              >
                {s.title[locale] ?? s.title.en}
              </Link>
            </li>
          ))}
        </ol>
      </nav>
      <div className="stories-main">{children}</div>
    </div>
  );
}
