import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";
import { cookies } from "next/headers";
import { Manrope, Unbounded } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";

/* Unbounded for display and Manrope for everything else — both carry Cyrillic, so an
   Uzbek Cyrillic headline is set in the same voice as a Latin one. */
const display = Unbounded({
  subsets: ["latin", "cyrillic"],
  weight: ["600", "700", "800"],
  variable: "--font-display",
  display: "swap",
});
const sans = Manrope({ subsets: ["latin", "cyrillic"], variable: "--font-sans", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Kanalchi", template: "%s · Kanalchi" },
  description: "A Telegram channel, readable and searchable.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const [locale, cookieStore] = await Promise.all([getLocale(), cookies()]);
  // An explicit choice wins; with no cookie the class is absent and CSS follows the system setting.
  const theme = cookieStore.get("theme")?.value;
  return (
    <html
      lang={locale}
      suppressHydrationWarning
      className={cn(sans.variable, display.variable, theme !== "light" && "dark", theme === "light" && "light")}
    >
      <body className="min-h-screen font-sans antialiased">
        <NextIntlClientProvider>{children}</NextIntlClientProvider>
      </body>
    </html>
  );
}
