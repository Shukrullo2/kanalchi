import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { LocaleSwitch } from "@/components/LocaleSwitch";
import { SignOut } from "@/components/SignOut";
import { TelegramLogin } from "@/components/TelegramLogin";
import { apiFetchOrNull } from "@/lib/api";
import { getMe } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const [me, t, tc] = await Promise.all([getMe(true), getTranslations("admin"), getTranslations("common")]);
  if (!me.authenticated || me.role !== "admin") {
    const widget = await apiFetchOrNull<{ bot_username: string | null }>("/api/auth/widget", { admin: true });
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-4 p-6 text-center">
        <h1 className="text-2xl font-semibold">Kanalchi · {t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("needLogin")}</p>
        <TelegramLogin botUsername={widget?.bot_username ?? null} dev={process.env.NODE_ENV === "development"} />
      </main>
    );
  }
  const items: [string, string][] = [
    ["/", t("overview")],
    ["/tenants", t("tenants")],
    ["/accounts", t("accounts")],
    ["/jobs", t("jobs")],
    ["/costs", t("costs")],
  ];
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4">
      <header className="flex items-center justify-between border-b py-4">
        <Link href="/" className="text-lg font-semibold">
          Kanalchi · {t("title")}
        </Link>
        <nav className="flex items-center gap-4 text-sm">
          {items.map(([href, label]) => (
            <Link key={href} href={href}>
              {label}
            </Link>
          ))}
          <Link href="/onboard" className="rounded bg-foreground px-3 py-1 text-background">
            {t("onboard")}
          </Link>
          <span className="text-muted-foreground">{me.name}</span>
          <SignOut label={tc("signOut")} />
          <LocaleSwitch />
        </nav>
      </header>
      <main className="flex-1 py-6">{children}</main>
    </div>
  );
}
