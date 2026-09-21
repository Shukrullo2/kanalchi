import { getTranslations } from "next-intl/server";

export default async function Page() {
  const t = await getTranslations("common");
  return (
    <div className="card-surface flex flex-col items-center gap-2 p-12 text-center">
      <span className="text-2xl" aria-hidden>
        ✳
      </span>
      <p className="text-sm text-muted-foreground">{t("comingSoon")}</p>
    </div>
  );
}
