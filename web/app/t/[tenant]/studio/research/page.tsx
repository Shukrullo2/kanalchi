import { getLocale, getTranslations } from "next-intl/server";
import { ChatView } from "@/components/chat/ChatView";

export default async function ResearchPage() {
  const [locale, t] = await Promise.all([getLocale(), getTranslations("research")]);

  return (
    <ChatView
      kind="research"
      suggestions={{ enabled: true, suggestions: [t("gaps"), t("covered"), t("popular"), t("quiet")] }}
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
