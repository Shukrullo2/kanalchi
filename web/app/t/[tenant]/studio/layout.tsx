import { getTranslations } from "next-intl/server";
import { SignOut } from "@/components/SignOut";
import { TelegramLogin } from "@/components/TelegramLogin";
import { apiFetch } from "@/lib/api";
import { getMe } from "@/lib/auth";
import type { TenantPublic } from "@/lib/types";

export default async function StudioLayout({ children }: { children: React.ReactNode }) {
  const [me, tenant, t, tc] = await Promise.all([getMe(), apiFetch<TenantPublic>("/api/tenant"), getTranslations("studio"), getTranslations("common")]);
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
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>
        <div className="flex items-center gap-3 text-sm">
          <span>{me.name}</span>
          <SignOut label={tc("signOut")} />
        </div>
      </div>
      {children}
    </div>
  );
}
