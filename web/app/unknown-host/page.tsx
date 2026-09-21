import { getTranslations } from "next-intl/server";

export default async function UnknownHost() {
  const t = await getTranslations("common");
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
      <div className="grid h-14 w-14 place-items-center rounded-2xl bg-surface-2 text-2xl">✳</div>
      <h1 className="text-xl font-semibold tracking-tight">Kanalchi</h1>
      <p className="text-sm text-muted-foreground">{t("unknownHost")}</p>
    </main>
  );
}
