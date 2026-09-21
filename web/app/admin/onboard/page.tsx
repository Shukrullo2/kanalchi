import { getTranslations } from "next-intl/server";
import { OnboardWizard } from "@/components/admin/OnboardWizard";
import { apiFetch } from "@/lib/api";
import type { TgAccount } from "@/lib/types";

export default async function OnboardPage() {
  const [accounts, t] = await Promise.all([
    apiFetch<TgAccount[]>("/api/admin/accounts", { admin: true }),
    getTranslations("admin"),
  ]);
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">{t("onboard")}</h1>
      <OnboardWizard accounts={accounts} />
    </div>
  );
}
