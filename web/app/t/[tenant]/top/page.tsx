import Link from "next/link";
import { FlameIcon } from "@/components/Icons";
import { PostCard } from "@/components/post/PostCard";
import { getLocale, getTranslations } from "next-intl/server";
import { apiFetch } from "@/lib/api";
import type { PostOut } from "@/lib/types";

export async function generateMetadata() {
  const t = await getTranslations("top");
  return { title: t("title") };
}

const METRICS = ["views", "reactions", "forwards", "engagement"] as const;
const RANGES = [
  { days: 30, key: "d30" },
  { days: 365, key: "y1" },
  { days: 3650, key: "all" },
] as const;

type Props = { searchParams: Promise<{ metric?: string; days?: string }> };

export default async function TopPage({ searchParams }: Props) {
  const sp = await searchParams;
  const metric = (METRICS as readonly string[]).includes(sp.metric ?? "") ? sp.metric! : "views";
  const days = Number(sp.days ?? 365);
  const [locale, t] = await Promise.all([getLocale(), getTranslations("top")]);
  const data = await apiFetch<{ items: PostOut[] }>(`/api/posts/top?metric=${metric}&days=${days}&limit=20`);

  return (
    <div className="space-y-5">
      <header className="flex items-center gap-2">
        <FlameIcon size={18} className="text-primary" />
        <h1 className="text-[1.75rem] font-semibold tracking-tight">{t("title")}</h1>
      </header>

      <div className="flex flex-wrap gap-3 text-xs">
        <div className="flex items-center rounded-full bg-surface-2 p-0.5">
          {METRICS.map((m) => (
            <Link
              key={m}
              href={`/top?metric=${m}&days=${days}`}
              className={`rounded-full px-2.5 py-1 transition-colors ${
                m === metric ? "bg-surface font-medium shadow-xs" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {t(m)}
            </Link>
          ))}
        </div>
        <div className="flex items-center rounded-full bg-surface-2 p-0.5">
          {RANGES.map((r) => (
            <Link
              key={r.days}
              href={`/top?metric=${metric}&days=${r.days}`}
              className={`rounded-full px-2.5 py-1 transition-colors ${
                r.days === days ? "bg-surface font-medium shadow-xs" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {t(r.key)}
            </Link>
          ))}
        </div>
      </div>

      <ol className="archive-grid mt-8">
        {data.items.map((p, i) => (
          <li key={p.id}>
            <PostCard post={p} locale={locale} rank={i + 1} />
          </li>
        ))}
      </ol>
    </div>
  );
}
