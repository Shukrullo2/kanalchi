import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { LandingShell } from "@/components/landing/LandingShell";
import { QuoteForm } from "@/components/signup/QuoteForm";
import { apiFetchOrNull } from "@/lib/api";
import { CONTACT_URL } from "@/lib/config";
import type { ChannelQuote } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("signup");
  return { title: { absolute: t("metaTitle") }, robots: { index: false } };
}

/** osor.uz/start: price a channel's import, no sign-in; `?c=<username>` shows an earlier quote. */
export default async function StartPage({
  searchParams,
}: {
  searchParams: Promise<{ c?: string | string[] }>;
}) {
  const { c } = await searchParams;
  const channel = typeof c === "string" && /^[A-Za-z][A-Za-z0-9_]{3,31}$/.test(c) ? c : null;
  const quote = channel
    ? await apiFetchOrNull<ChannelQuote>(`/api/signup/quote/${channel.toLowerCase()}`)
    : null;
  return (
    <LandingShell>
      <QuoteForm initialChannel={channel} initialQuote={quote} contactUrl={CONTACT_URL || null} />
    </LandingShell>
  );
}
