import { getRequestConfig } from "next-intl/server";
import { cookies, headers } from "next/headers";
import { DEFAULT_LOCALE, LOCALES, type Locale } from "@/lib/config";

function pick(candidate: string | undefined | null): Locale | null {
  if (!candidate) return null;
  const short = candidate.toLowerCase().split("-")[0];
  return (LOCALES as readonly string[]).includes(short) ? (short as Locale) : null;
}

/** The visitor's own choice (the locale switch sets the cookie), else the channel's language,
 * else Uzbek. The browser's Accept-Language is deliberately ignored: the audience is in
 * Uzbekistan, and many of their browsers are set to English or Russian. */
export default getRequestConfig(async () => {
  const c = await cookies();
  const h = await headers();
  const fromCookie = pick(c.get("locale")?.value);
  const fromTenant = pick(h.get("x-tenant-lang"));
  const locale = fromCookie ?? fromTenant ?? DEFAULT_LOCALE;
  return { locale, messages: (await import(`../messages/${locale}.json`)).default };
});
