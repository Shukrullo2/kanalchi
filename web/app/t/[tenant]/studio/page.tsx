import { getTranslations } from "next-intl/server";

export default async function StudioHome() {
  const t = await getTranslations("common");
  return <p className="text-muted-foreground">ideas · research · drafts — {t("comingSoon")}</p>;
}
