import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { AdminNav } from "@/components/admin/AdminNav";
import { TelegramLogin } from "@/components/TelegramLogin";
import { apiFetchOrNull } from "@/lib/api";
import { getMe } from "@/lib/auth";

export const dynamic = "force-dynamic";
export const metadata = { title: "Admin" };

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const [me, t] = await Promise.all([getMe(true), getTranslations("admin")]);

  if (!me.authenticated || me.role !== "admin") {
    const widget = await apiFetchOrNull<{ bot_username: string | null }>("/api/auth/widget", { admin: true });
    return (
      <main className="mx-auto flex min-h-screen max-w-sm flex-col items-center justify-center gap-5 px-6 text-center">
        <div className="grid h-12 w-12 place-items-center rounded-2xl bg-primary text-lg font-semibold text-primary-foreground">
          K
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Kanalchi</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("needLogin")}</p>
        </div>
        <TelegramLogin botUsername={widget?.bot_username ?? null} dev={process.env.NODE_ENV === "development"} />
      </main>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <AdminNav
        name={me.name}
        items={[
          { href: "/", label: t("overview") },
          { href: "/tenants", label: t("tenants") },
          { href: "/accounts", label: t("accounts") },
          { href: "/jobs", label: t("jobs") },
          { href: "/costs", label: t("costs") },
        ]}
        onboardLabel={t("onboard")}
      />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:py-8">{children}</main>
      <footer className="border-t">
        <div className="mx-auto w-full max-w-5xl px-4 py-5 text-xs text-muted-foreground">
          Kanalchi admin ·{" "}
          <Link href="/jobs" className="link-quiet underline">
            job queue
          </Link>
        </div>
      </footer>
    </div>
  );
}
