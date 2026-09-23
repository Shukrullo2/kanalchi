"use client";

import { useEffect } from "react";

/**
 * Last-resort boundary: a failed server call (API down, unexpected 5xx) lands here instead
 * of the framework's blank error screen. Kept dependency-free so it renders when nothing
 * else does.
 */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-xl font-semibold tracking-tight">Something went wrong</h1>
      <p className="text-sm text-muted-foreground">
        The page could not be loaded right now. It is usually temporary.
      </p>
      <button onClick={reset} className="btn-primary">
        Try again
      </button>
    </main>
  );
}
