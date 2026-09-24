import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { LandingShell } from "@/components/landing/LandingShell";
import { StartHome } from "@/components/signup/StartHome";
import { TelegramLogin } from "@/components/TelegramLogin";
import { apiFetchOrNull } from "@/lib/api";
import { getMe } from "@/lib/auth";
import type { SignupChannel } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("signup");
  return { title: { absolute: t("metaTitle") }, robots: { index: false } };
}

/** osor.uz/start: sign in with Telegram, then your channels and the form that adds one. */
export default async function StartPage() {
  const [me, t, common] = await Promise.all([
    getMe(),
    getTranslations("signup"),
    getTranslations("common"),
  ]);

  if (!me.authenticated || me.role !== "user") {
    const widget = await apiFetchOrNull<{ bot_username: string | null }>(
      "/api/auth/widget",
    );
    return (
      <LandingShell>
        <section className="shell landing-section pt-10 sm:pt-14">
          <div className="landing-final items-center text-center">
            <p className="eyebrow">Osor</p>
            <h1 className="landing-h2">{t("title")}</h1>
            <p>{t("needLogin")}</p>
            <TelegramLogin
              botUsername={widget?.bot_username ?? null}
              dev={process.env.NODE_ENV === "development"}
              notConfigured={common("loginNotConfigured")}
            />
          </div>
        </section>
      </LandingShell>
    );
  }

  const channels =
    (await apiFetchOrNull<SignupChannel[]>("/api/signup/channels")) ?? [];
  return (
    <LandingShell>
      <StartHome channels={channels} name={me.name} />
    </LandingShell>
  );
}
