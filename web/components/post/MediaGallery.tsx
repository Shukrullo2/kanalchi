/* eslint-disable @next/next/no-img-element -- media is served pre-thumbnailed from MinIO on the tenant domain */
import { ExternalIcon } from "@/components/Icons";
import type { MediaOut } from "@/lib/types";

function Item({ m, tall }: { m: MediaOut; tall: boolean }) {
  const src = m.url ?? m.thumb_url;
  const frame = tall ? "max-h-[70vh]" : "aspect-square h-full w-full object-cover";

  if (m.status === "too_large" || m.status === "protected" || (!src && m.external_url)) {
    return (
      <a
        href={m.external_url ?? "#"}
        target="_blank"
        rel="noreferrer"
        className="group relative flex min-h-32 flex-col items-center justify-center gap-2 overflow-hidden rounded-lg border border-dashed bg-surface-2 p-6 text-center"
      >
        {m.thumb_url ? (
          <img src={m.thumb_url} alt="" loading="lazy" className="absolute inset-0 h-full w-full object-cover opacity-30 blur-[1px]" />
        ) : null}
        <span className="relative flex items-center gap-1.5 text-xs text-muted-foreground group-hover:text-foreground">
          {m.kind}
          {m.size_bytes ? ` · ${Math.round(m.size_bytes / 1048576)} MB` : ""} · open in Telegram
          <ExternalIcon size={12} />
        </span>
      </a>
    );
  }
  if (!src) return null;

  if (m.kind === "video" || m.kind === "animation") {
    return (
      <video
        controls
        preload="none"
        playsInline
        poster={m.thumb_url ?? undefined}
        className={`w-full rounded-lg bg-black ${tall ? "max-h-[70vh]" : "aspect-square object-cover"}`}
        src={m.url ?? undefined}
      />
    );
  }
  if (m.kind === "voice" || m.kind === "audio") {
    return <audio controls preload="none" src={m.url ?? undefined} className="w-full" />;
  }
  if (m.kind === "document") {
    return (
      <a
        href={m.url ?? "#"}
        target="_blank"
        rel="noreferrer"
        className="flex items-center gap-2 rounded-lg border bg-surface-2 p-3 text-sm hover:border-border-strong"
      >
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-primary/10 text-primary">↓</span>
        <span className="truncate">{m.file_name ?? "document"}</span>
      </a>
    );
  }
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      width={m.width ?? undefined}
      height={m.height ?? undefined}
      className={`rounded-lg bg-surface-2 ${frame}`}
    />
  );
}

export function MediaGallery({ media }: { media: MediaOut[] }) {
  if (media.length === 0) return null;
  if (media.length === 1) return <Item m={media[0]} tall />;
  return (
    <div className={`grid gap-1.5 ${media.length === 2 ? "grid-cols-2" : "grid-cols-2 sm:grid-cols-3"}`}>
      {media.map((m) => (
        <Item key={m.id} m={m} tall={false} />
      ))}
    </div>
  );
}
