import { getTranslations } from "next-intl/server";
import { LocaleSwitch } from "@/components/LocaleSwitch";
import { SignOut } from "@/components/SignOut";
import { ThemeToggle } from "@/components/ThemeToggle";
import { getMe } from "@/lib/auth";

/** The example channel the landing page points at as proof. */
export const EXAMPLE_HOST = "the-bakiroo.uz";
export const EXAMPLE_URL = `https://${EXAMPLE_HOST}`;

/**
 * Header, footer and page frame shared by the landing page and the sign-up pages on the
 * platform domain. The header's right-hand button is "get started" for a visitor and the
 * signed-in name plus sign-out for a blogger who already registered.
 */
export async function LandingShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const [t, common, me] = await Promise.all([
    getTranslations("landing"),
    getTranslations("common"),
    getMe(),
  ]);
  const signedIn = me.authenticated && me.role === "user";

  return (
    <div className="landing">
      <div className="sticky top-0 z-40 pt-3">
        <div className="shell">
          <header className="topbar">
            <a href="/" className="landing-logo" aria-label="Osor">
              <span className="landing-mark" aria-hidden>
                O
              </span>
              Osor
            </a>
            <div className="ml-auto flex items-center gap-1.5">
              <LocaleSwitch />
              <ThemeToggle label={common("theme")} />
              {signedIn ? (
                <>
                  <a
                    href="/start"
                    className="btn-ghost ml-1 hidden h-9 px-3 text-sm sm:inline-flex"
                  >
                    {me.name}
                  </a>
                  <SignOut label={common("signOut")} />
                </>
              ) : (
                <a href="/start" className="btn-primary ml-1 h-9 px-4 text-sm">
                  {t("ctaStart")}
                </a>
              )}
            </div>
          </header>
        </div>
      </div>

      <main>{children}</main>

      <footer className="mt-16 border-t">
        <div className="shell flex flex-wrap items-center gap-x-5 gap-y-2 py-6 text-xs text-muted-foreground">
          <span>© Osor</span>
          <a
            href={EXAMPLE_URL}
            className="link-quiet"
            target="_blank"
            rel="noreferrer"
          >
            {EXAMPLE_HOST}
          </a>
          <span className="ml-auto">{common("madeBy")}</span>
        </div>
      </footer>
    </div>
  );
}
