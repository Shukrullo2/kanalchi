import { getTranslations } from "next-intl/server";
import { OnboardWizard } from "@/components/admin/OnboardWizard";
import { apiFetch, apiFetchOrNull } from "@/lib/api";
import type { AdminTenant, Checklist, TgAccount } from "@/lib/types";

type Props = { searchParams: Promise<{ tenant?: string }> };

export default async function OnboardPage({ searchParams }: Props) {
  const sp = await searchParams;
  const id = Number(sp.tenant);
  const [accounts, t, tenant, checklist] = await Promise.all([
    apiFetch<TgAccount[]>("/api/admin/accounts", { admin: true }),
    getTranslations("admin"),
    id ? apiFetchOrNull<AdminTenant>(`/api/admin/tenants/${id}`, { admin: true }) : null,
    id ? apiFetchOrNull<Checklist>(`/api/admin/tenants/${id}/checklist`, { admin: true }) : null,
  ]);
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">{t("onboard")}</h1>
      <OnboardWizard accounts={accounts} resume={tenant && checklist ? { tenant, checklist } : null} />
    </div>
  );
}
