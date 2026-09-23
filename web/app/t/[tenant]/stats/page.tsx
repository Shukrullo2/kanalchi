import { permanentRedirect } from "next/navigation";

/**
 * The statistics are the front page now. Keep the old address working: it was
 * in the navigation, in the sitemap, and in anything anyone bookmarked.
 */
export default function StatsPage(): never {
  permanentRedirect("/");
}
