import { getTranslations } from "next-intl/server";

export default async function Page() {
  const t = await getTranslations("common");
  return <p className="text-muted-foreground">accounts — {t("comingSoon")}</p>;
}
