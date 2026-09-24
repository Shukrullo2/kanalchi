import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { LandingShell } from "@/components/landing/LandingShell";
import { OnboardingFlow } from "@/components/signup/OnboardingFlow";
import { apiFetchOrNull } from "@/lib/api";
import { getMe } from "@/lib/auth";
import { CONTACT_URL } from "@/lib/config";
import type { PlanCatalogue, SignupChannel } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("signup");
  return { title: { absolute: t("metaTitle") }, robots: { index: false } };
}

/** osor.uz/start/<id>: one channel's onboarding checklist. */
export default async function ChannelStartPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const me = await getMe();
  if (!me.authenticated || me.role !== "user") redirect("/start");

  const [channel, catalogue, widget] = await Promise.all([
    apiFetchOrNull<SignupChannel>(`/api/signup/channels/${id}`),
    apiFetchOrNull<PlanCatalogue>("/api/signup/plans"),
    apiFetchOrNull<{ bot_username: string | null }>("/api/auth/widget"),
  ]);
  if (!channel) notFound();

  return (
    <LandingShell>
      <OnboardingFlow
        initial={channel}
        plans={catalogue?.plans ?? []}
        botUsername={widget?.bot_username ?? null}
        contactUrl={CONTACT_URL || null}
      />
    </LandingShell>
  );
}
