"use client";

import { useRouter } from "next/navigation";

export function SignOut({ label }: { label: string }) {
  const router = useRouter();
  return (
    <button
      className="text-sm text-muted-foreground hover:text-foreground"
      onClick={async () => {
        await fetch("/api/auth/logout", { method: "POST" });
        router.refresh();
      }}
    >
      {label}
    </button>
  );
}
