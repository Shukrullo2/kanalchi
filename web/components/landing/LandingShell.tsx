import { getTranslations } from "next-intl/server";
import { LocaleSwitch } from "@/components/LocaleSwitch";
import { ThemeToggle } from "@/components/ThemeToggle";

/** The example channel the landing page points at as proof. */
export const EXAMPLE_HOST = "the-bakiroo.uz";
export const EXAMPLE_URL = `https://${EXAMPLE_HOST}`;

/**
 * Header, footer and page frame shared by the landing page and the sign-up pages on the
 * platform domain. The header's right-hand button is always "get started": pricing a channel
 * needs no account.
 */
export async function LandingShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const [t, common] = await Promise.all([
    getTranslations("landing"),
    getTranslations("common"),
  ]);

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
              <a href="/start" className="btn-primary ml-1 h-9 px-4 text-sm">
                {t("ctaStart")}
              </a>
            </div>
          </header>
        </div>
      </div>

      <main>{children}</main>

      <footer className="mt-16 border-t">
        <p className="shell landing-footnote">{t("footnote")}</p>
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
