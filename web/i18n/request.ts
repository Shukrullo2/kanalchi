import { getRequestConfig } from "next-intl/server";
import { cookies, headers } from "next/headers";
import { DEFAULT_LOCALE, LOCALES, type Locale } from "@/lib/config";

function pick(candidate: string | undefined | null): Locale | null {
  if (!candidate) return null;
  const short = candidate.toLowerCase().split("-")[0];
  return (LOCALES as readonly string[]).includes(short) ? (short as Locale) : null;
}

export default getRequestConfig(async () => {
  const c = await cookies();
  const h = await headers();
  const fromCookie = pick(c.get("locale")?.value);
  const fromTenant = pick(h.get("x-tenant-lang"));
  const fromAccept = (h.get("accept-language") ?? "")
    .split(",")
    .map((s) => pick(s.trim().split(";")[0]))
    .find(Boolean) ?? null;
  const locale = fromCookie ?? fromTenant ?? fromAccept ?? DEFAULT_LOCALE;
  return { locale, messages: (await import(`../messages/${locale}.json`)).default };
});
