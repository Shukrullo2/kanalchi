import { getTranslations } from "next-intl/server";
import { apiFetch } from "@/lib/api";
import type { TenantPublic } from "@/lib/types";

export default async function TenantHome() {
  const [tenant, t, tc] = await Promise.all([apiFetch<TenantPublic>("/api/tenant"), getTranslations("home"), getTranslations("common")]);
  return (
    <div className="space-y-4">
      {tenant.about ? <p className="text-muted-foreground">{tenant.about}</p> : null}
      <p className="text-sm text-muted-foreground">{tc("posts", { count: tenant.post_count ?? 0 })}</p>
      {(tenant.post_count ?? 0) === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center">
          <h2 className="font-medium">{t("emptyTitle")}</h2>
          <p className="text-sm text-muted-foreground">{t("emptyBody")}</p>
        </div>
      ) : null}
    </div>
  );
}
