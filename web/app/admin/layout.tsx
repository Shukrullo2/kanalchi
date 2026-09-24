import Link from "@/components/AppLink";
import { getTranslations } from "next-intl/server";
import { AdminNav } from "@/components/admin/AdminNav";
import { TelegramLogin } from "@/components/TelegramLogin";
import { apiFetchOrNull } from "@/lib/api";
import { getMe } from "@/lib/auth";

export const dynamic = "force-dynamic";
export const metadata = { title: "Admin" };

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [me, t, common] = await Promise.all([
    getMe(true),
    getTranslations("admin"),
    getTranslations("common"),
  ]);

  if (!me.authenticated || me.role !== "admin") {
    const widget = await apiFetchOrNull<{ bot_username: string | null }>(
      "/api/auth/widget",
      { admin: true },
    );
    return (
      <main className="mx-auto flex min-h-screen max-w-sm flex-col items-center justify-center gap-5 px-6 text-center">
        <div className="grid h-11 w-11 place-items-center rounded-xl bg-primary text-lg font-semibold text-primary-foreground">
          K
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Kanalchi</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("needLogin")}</p>
        </div>
        <TelegramLogin
          botUsername={widget?.bot_username ?? null}
          dev={process.env.NODE_ENV === "development"}
          notConfigured="The login bot is not set up for this domain."
        />
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
          { href: "/signups", label: t("signups") },
          { href: "/accounts", label: t("accounts") },
          { href: "/jobs", label: t("jobs") },
          { href: "/costs", label: t("costs") },
        ]}
        onboardLabel={t("onboard")}
      />
      <main className="shell-wide flex-1 py-7 sm:py-9">{children}</main>
      <footer className="mt-12 border-t">
        <div className="shell-wide flex items-center gap-5 py-5 text-xs text-muted-foreground">
          <Link href="/jobs" className="link-quiet">
            Job queue
          </Link>
          <span className="ml-auto">{common("madeBy")}</span>
        </div>
      </footer>
    </div>
  );
}
