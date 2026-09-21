import { getTranslations } from "next-intl/server";
import { StudioNav } from "@/components/studio/StudioNav";
import { TelegramLogin } from "@/components/TelegramLogin";
import { apiFetch } from "@/lib/api";
import { getMe } from "@/lib/auth";
import type { TenantPublic } from "@/lib/types";

export const metadata = { title: "Studio", robots: { index: false } };

export default async function StudioLayout({ children }: { children: React.ReactNode }) {
  const [me, tenant, t] = await Promise.all([
    getMe(),
    apiFetch<TenantPublic>("/api/tenant"),
    getTranslations("studio"),
  ]);

  if (!me.authenticated || (me.role !== "owner" && me.role !== "editor")) {
    return (
      <div className="card-surface mx-auto max-w-md space-y-4 p-8 text-center">
        <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("needLogin")}</p>
        <TelegramLogin botUsername={tenant.bot_username} dev={process.env.NODE_ENV === "development"} />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>
        <span className="text-xs text-muted-foreground">{me.name}</span>
      </div>
      <StudioNav />
      {children}
    </div>
  );
}
