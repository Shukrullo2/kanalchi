import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";
import { cookies } from "next/headers";
import { Golos_Text, JetBrains_Mono, Spectral } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";

/* Golos Text was cut for Russian-language public-service typography — ministries, decrees,
   notices — which is the register this content actually lives in. Spectral carries the post
   bodies because Telegram marks italics and it has real ones, in Cyrillic as well as Latin. */
const sans = Golos_Text({ subsets: ["latin", "cyrillic"], variable: "--font-sans", display: "swap" });
const serif = Spectral({
  subsets: ["latin", "cyrillic"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-serif",
  display: "swap",
});
const mono = JetBrains_Mono({ subsets: ["latin", "cyrillic"], variable: "--font-mono", display: "swap" });

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
      className={cn(sans.variable, serif.variable, mono.variable, theme === "dark" && "dark", theme === "light" && "light")}
    >
      <body className="min-h-screen font-sans antialiased">
        <NextIntlClientProvider>{children}</NextIntlClientProvider>
      </body>
    </html>
  );
}
