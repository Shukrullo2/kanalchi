import Link from "next/link";
import { PostCard } from "@/components/post/PostCard";
import { apiFetch } from "@/lib/api";
import type { PostOut } from "@/lib/types";

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
  const data = await apiFetch<{ items: PostOut[] }>(`/api/posts/top?metric=${metric}&days=${days}&limit=20`);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 text-sm">
        <div className="flex gap-2">
          {METRICS.map((m) => (
            <Link key={m} href={`/top?metric=${m}&days=${days}`} className={m === metric ? "font-semibold" : "text-muted-foreground"}>
              {m}
            </Link>
          ))}
        </div>
        <div className="flex gap-2">
          {RANGES.map((r) => (
            <Link
              key={r.days}
              href={`/top?metric=${metric}&days=${r.days}`}
              className={r.days === days ? "font-semibold" : "text-muted-foreground"}
            >
              {r.label}
            </Link>
          ))}
        </div>
      </div>
      {data.items.map((p) => (
        <PostCard key={p.id} post={p} />
      ))}
    </div>
  );
}
