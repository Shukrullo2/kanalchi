import { getLocale, getTranslations } from "next-intl/server";
import { ChatView } from "@/components/chat/ChatView";
import { apiFetchOrNull } from "@/lib/api";
import type { ChatSuggestions } from "@/lib/types";

export const metadata = { title: "Ask", robots: { index: false } };

export default async function ChatPage() {
  const [suggestions, locale, t] = await Promise.all([
    apiFetchOrNull<ChatSuggestions>("/api/chat/suggestions"),
    getLocale(),
    getTranslations("chat"),
  ]);

  return (
    <ChatView
      suggestions={suggestions ?? { suggestions: [], enabled: true }}
      locale={locale}
      labels={{
        placeholder: t("placeholder"),
        intro: t("intro"),
        send: t("send"),
        thinking: t("thinking"),
        disabled: t("disabled"),
        sources: t("sources"),
      }}
    />
  );
}
