import Link from "next/link";
import { FlameIcon } from "@/components/Icons";
import { PostCard } from "@/components/post/PostCard";
import { getLocale } from "next-intl/server";
import { apiFetch } from "@/lib/api";
import type { PostOut } from "@/lib/types";

export const metadata = { title: "Top posts" };

const METRICS = ["views", "reactions", "forwards", "engagement"] as const;
const RANGES = [
  { days: 30, label: "30d" },
  { days: 365, label: "1y" },
  { days: 3650, label: "all" },
];

type Props = { searchParams: Promise<{ metric?: string; days?: string }> };

export default async function TopPage({ searchParams }: Props) {
  const sp = await searchParams;
  const metric = (METRICS as readonly string[]).includes(sp.metric ?? "") ? sp.metric! : "views";
  const days = Number(sp.days ?? 365);
  const locale = await getLocale();
  const data = await apiFetch<{ items: PostOut[] }>(`/api/posts/top?metric=${metric}&days=${days}&limit=20`);

  return (
    <div className="space-y-5">
      <header className="flex items-center gap-2">
        <FlameIcon size={18} className="text-primary" />
        <h1 className="text-xl font-semibold tracking-tight">Top posts</h1>
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
              {m}
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
              {r.label}
            </Link>
          ))}
        </div>
      </div>

      <ol className="space-y-3.5">
        {data.items.map((p, i) => (
          <li key={p.id} className="relative animate-rise" style={{ animationDelay: `${Math.min(i, 8) * 25}ms` }}>
            <span className="absolute -left-1 -top-1 z-10 grid h-6 w-6 place-items-center rounded-full bg-primary text-[0.7rem] font-semibold text-primary-foreground shadow-sm">
              {i + 1}
            </span>
            <PostCard post={p} locale={locale} />
          </li>
        ))}
      </ol>
    </div>
  );
}
