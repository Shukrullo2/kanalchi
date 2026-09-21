/* eslint-disable @next/next/no-img-element -- media is served pre-thumbnailed from MinIO on the tenant domain */
import type { MediaOut } from "@/lib/types";

function Item({ m }: { m: MediaOut }) {
  const src = m.url ?? m.thumb_url;
  if (m.status === "too_large" || m.status === "protected" || (!src && m.external_url)) {
    return (
      <a
        href={m.external_url ?? "#"}
        target="_blank"
        rel="noreferrer"
        className="flex flex-col items-center justify-center gap-1 rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground hover:text-foreground"
      >
        {m.thumb_url ? <img src={m.thumb_url} alt="" className="max-h-64 rounded" loading="lazy" /> : null}
        <span>
          {m.kind} · {m.size_bytes ? `${Math.round(m.size_bytes / 1048576)} MB · ` : ""}open in Telegram ↗
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
        poster={m.thumb_url ?? undefined}
        className="max-h-[70vh] w-full rounded-lg bg-black"
        src={m.url ?? undefined}
      />
    );
  }
  if (m.kind === "voice" || m.kind === "audio") {
    return <audio controls preload="none" src={m.url ?? undefined} className="w-full" />;
  }
  if (m.kind === "document") {
    return (
      <a href={m.url ?? "#"} target="_blank" rel="noreferrer" className="block rounded-lg border p-3 text-sm underline">
        {m.file_name ?? "document"}
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
      className="max-h-[70vh] w-full rounded-lg object-cover"
    />
  );
}

export function MediaGallery({ media }: { media: MediaOut[] }) {
  if (media.length === 0) return null;
  if (media.length === 1) return <Item m={media[0]} />;
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {media.map((m) => (
        <Item key={m.id} m={m} />
      ))}
    </div>
  );
}
