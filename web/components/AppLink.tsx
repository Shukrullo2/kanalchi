import NextLink from "next/link";
import type { ComponentProps } from "react";

/**
 * `next/link` with viewport prefetching off.
 *
 * Every page here is dynamic and a tag page lists dozens of links (tags, searches, graphs,
 * stories). With prefetching on, opening one fired fifty-odd server renders in the same
 * second, which exhausted the API's database pool and pushed it past its memory limit on a
 * 2-core host. Navigation still renders on click; pass `prefetch` explicitly to opt back in.
 */
export default function Link({ prefetch = false, ...props }: ComponentProps<typeof NextLink>) {
  return <NextLink prefetch={prefetch} {...props} />;
}
