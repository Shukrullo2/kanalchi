import { getTranslations } from "next-intl/server";

export default async function UnknownHost() {
  const t = await getTranslations("common");
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center gap-2 p-6 text-center">
      <h1 className="text-2xl font-semibold">Kanalchi</h1>
      <p className="text-muted-foreground">{t("unknownHost")}</p>
    </main>
  );
}
