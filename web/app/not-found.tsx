import Link from "next/link";
import { getTranslations } from "next-intl/server";

export default async function NotFound() {
  const t = await getTranslations("common");
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
      <p className="text-5xl font-semibold tracking-tight text-muted-foreground/40">404</p>
      <p className="text-sm text-muted-foreground">{t("notFound")}</p>
      <Link href="/" className="btn-ghost mt-2">
        {t("backToChannel")}
      </Link>
    </main>
  );
}
