import { initialsGradient } from "@/lib/format";

export function Avatar({ src, name, size = 40 }: { src?: string | null; name: string; size?: number }) {
  const { initials, style } = initialsGradient(name || "Kanal");
  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- served from MinIO on the tenant domain
      <img
        src={src}
        alt=""
        width={size}
        height={size}
        className="shrink-0 rounded-full object-cover ring-1 ring-border"
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <span
      aria-hidden
      className="grid shrink-0 place-items-center rounded-full font-semibold text-white"
      style={{ ...style, width: size, height: size, fontSize: size * 0.38 }}
    >
      {initials}
    </span>
  );
}
