import { getTranslations } from "next-intl/server";

export async function generateMetadata() {
  const t = await getTranslations("stories");
  return { title: t("title") };
}

/**
 * What fills the right-hand side before a story has been picked.
 *
 * On a phone this is never seen: there the list in the layout is the page, and
 * the stylesheet hides this half until a story is chosen.
 */
export default async function StoriesPage() {
  const t = await getTranslations("stories");

  return (
    <div className="stories-intro">
      <h1 className="text-[1.75rem] font-semibold tracking-tight sm:text-[2rem]">{t("title")}</h1>
      <p className="mt-2 max-w-[60ch] text-[0.9375rem] text-muted-foreground">{t("intro")}</p>
      <p className="mt-6 text-sm text-muted-foreground">{t("pick")}</p>
    </div>
  );
}
