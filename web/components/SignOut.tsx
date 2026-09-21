"use client";

import { useRouter } from "next/navigation";

export function SignOut({ label }: { label: string }) {
  const router = useRouter();
  return (
    <button
      title="Sign out"
      aria-label="Sign out"
      className="grid h-8 min-w-8 place-items-center rounded-full px-2 text-xs text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
      onClick={async () => {
        await fetch("/api/auth/logout", { method: "POST" });
        router.refresh();
      }}
    >
      {label}
    </button>
  );
}
