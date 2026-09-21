"use client";

import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { LOCALES } from "@/lib/config";

export function LocaleSwitch() {
  const locale = useLocale();
  const router = useRouter();
  return (
    <div className="flex gap-1 text-xs">
      {LOCALES.map((l) => (
        <button
          key={l}
          className={l === locale ? "font-semibold" : "text-muted-foreground hover:text-foreground"}
          onClick={() => {
            document.cookie = `locale=${l}; path=/; max-age=31536000; samesite=lax`;
            router.refresh();
          }}
        >
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
