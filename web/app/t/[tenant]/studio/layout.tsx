import { getTranslations } from "next-intl/server";
import { PlanGate } from "@/components/studio/PlanGate";
import { StudioNav } from "@/components/studio/StudioNav";
import { TelegramLogin } from "@/components/TelegramLogin";
import { apiFetch } from "@/lib/api";
import { getMe } from "@/lib/auth";
import { PLATFORM_DOMAIN } from "@/lib/config";
import type { TenantPublic } from "@/lib/types";

export async function generateMetadata() {
  const t = await getTranslations("studio");
  return { title: t("title"), robots: { index: false } };
}

export default async function StudioLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [me, tenant, t, common] = await Promise.all([
    getMe(),
    apiFetch<TenantPublic>("/api/tenant"),
    getTranslations("studio"),
    getTranslations("common"),
  ]);

  if (!me.authenticated || (me.role !== "owner" && me.role !== "editor")) {
    return (
      <div className="mx-auto max-w-md space-y-4 py-16 text-center">
        <h1 className="text-[1.75rem] font-semibold tracking-tight">
          {t("title")}
        </h1>
        <p className="text-sm text-muted-foreground">{t("needLogin")}</p>
        <TelegramLogin
          botUsername={tenant.bot_username}
          dev={process.env.NODE_ENV === "development"}
          notConfigured={common("loginNotConfigured")}
        />
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-[1.75rem] font-semibold tracking-tight">
          {t("title")}
        </h1>
        <span className="text-xs text-muted-foreground">{me.name}</span>
      </div>
      <StudioNav />
      <div className="pt-6">
        <PlanGate
          writingTools={tenant.writing_tools ?? true}
          plansUrl={
            PLATFORM_DOMAIN ? `https://${PLATFORM_DOMAIN}/#pricing` : "/"
          }
        >
          {children}
        </PlanGate>
      </div>
    </div>
  );
}
