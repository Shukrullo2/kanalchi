import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
      <p className="text-5xl font-semibold tracking-tight text-muted-foreground/40">404</p>
      <p className="text-sm text-muted-foreground">This page does not exist.</p>
      <Link href="/" className="btn-ghost mt-2">
        Back to the channel
      </Link>
    </main>
  );
}
