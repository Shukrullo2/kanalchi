"use client";

import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { LOCALES } from "@/lib/config";

export function LocaleSwitch() {
  const locale = useLocale();
  const router = useRouter();
  return (
    <div className="flex items-center rounded-full bg-surface-2 p-0.5 text-[0.68rem] font-medium">
      {LOCALES.map((l) => (
        <button
          key={l}
          onClick={() => {
            document.cookie = `locale=${l}; path=/; max-age=31536000; samesite=lax`;
            router.refresh();
          }}
          className={`rounded-full px-1.5 py-0.5 transition-colors ${
            l === locale ? "bg-surface text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
          }`}
          aria-current={l === locale}
        >
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
