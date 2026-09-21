import { getTranslations } from "next-intl/server";
import { AccountsManager } from "@/components/admin/AccountsManager";
import { apiFetch } from "@/lib/api";
import type { TgAccount } from "@/lib/types";

export default async function AccountsPage() {
  const [accounts, t] = await Promise.all([
    apiFetch<TgAccount[]>("/api/admin/accounts", { admin: true }),
    getTranslations("admin"),
  ]);
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">{t("accounts")}</h1>
      <AccountsManager initial={accounts} />
    </div>
  );
}
