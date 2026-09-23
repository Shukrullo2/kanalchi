import { getTranslations } from "next-intl/server";
import { ArchiveControls } from "@/components/ArchiveControls";
import { Timeline } from "@/components/post/Timeline";
import { apiFetch } from "@/lib/api";
import type { PostPage, TenantPublic } from "@/lib/types";

export async function generateMetadata() {
  const t = await getTranslations("archive");
  return { title: t("title") };
}

/** 12948 → "12 948": a thin space per thousand, the same in every locale we serve. */
function groupThousands(n: number): string {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

/**
 * The archive itself, newest first.
 *
 * The channel's name, bio and numbers belong to the front page; this one opens
 * straight onto the search field and the posts, because someone who has got
 * here already knows whose archive they are in.
 */
export default async function ArchivePage() {
  const [tenant, page, t, tc] = await Promise.all([
    apiFetch<TenantPublic>("/api/tenant"),
    apiFetch<PostPage>("/api/posts?limit=24"),
    getTranslations("archive"),
    getTranslations("common"),
  ]);

  return (
    <div>
      <header className="pb-5 pt-2">
        <h1 className="text-[1.75rem] font-semibold tracking-tight sm:text-[2rem]">{t("title")}</h1>
      </header>

      <div className="border-b pb-5">
        <ArchiveControls
          placeholder={t("searchPlaceholder")}
          sorts={[
            { href: "/posts", label: t("sortNewest"), active: true },
            { href: "/top", label: t("sortTop") },
          ]}
          totalLabel={t("totalPosts", { count: groupThousands(tenant.post_count ?? 0) })}
        />
      </div>

      {page.items.length === 0 ? (
        <div className="py-16 text-center">
          <h2 className="text-xl">{t("emptyTitle")}</h2>
          <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">{t("emptyBody")}</p>
        </div>
      ) : (
        <div className="mt-6">
          <Timeline initial={page} loadMoreLabel={tc("loadMore")} />
        </div>
      )}
    </div>
  );
}
