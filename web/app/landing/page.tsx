import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import {
  CalendarIcon,
  ChartIcon,
  ChatIcon,
  GlobeIcon,
  IdeaIcon,
  MapIcon,
  PenIcon,
  SearchIcon,
  SendIcon,
  TagIcon,
} from "@/components/Icons";
import { LocaleSwitch } from "@/components/LocaleSwitch";
import { ThemeToggle } from "@/components/ThemeToggle";
import { CONTACT_URL } from "@/lib/config";

/** The live channel the page points at as proof. */
const EXAMPLE_URL = "https://the-bakiroo.uz";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("landing");
  return { title: { absolute: t("metaTitle") }, description: t("metaDescription") };
}

/**
 * osor.uz: what the service does, for the people who read a channel and for the
 * person who writes it, and one way to get in touch. Every button that asks for
 * something goes to the same place, the platform owner's Telegram.
 */
export default async function Landing() {
  const [t, common] = await Promise.all([getTranslations("landing"), getTranslations("common")]);
  const contact = CONTACT_URL || "#contact";
  const external = CONTACT_URL ? { target: "_blank", rel: "noreferrer" } : {};

  const readers = [
    { icon: GlobeIcon, title: t("f1t"), body: t("f1b") },
    { icon: TagIcon, title: t("f2t"), body: t("f2b") },
    { icon: SearchIcon, title: t("f3t"), body: t("f3b") },
    { icon: ChatIcon, title: t("f4t"), body: t("f4b") },
    { icon: MapIcon, title: t("f5t"), body: t("f5b") },
    { icon: ChartIcon, title: t("f6t"), body: t("f6b") },
  ];
  const studio = [
    { icon: IdeaIcon, title: t("s1t"), body: t("s1b") },
    { icon: PenIcon, title: t("s2t"), body: t("s2b") },
    { icon: SearchIcon, title: t("s3t"), body: t("s3b") },
    { icon: CalendarIcon, title: t("s4t"), body: t("s4b") },
  ];
  const steps = [
    { title: t("p1t"), body: t("p1b") },
    { title: t("p2t"), body: t("p2b") },
    { title: t("p3t"), body: t("p3b") },
  ];

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
              <a href={contact} {...external} className="btn-primary ml-1 hidden h-9 px-4 text-sm sm:inline-flex">
                {t("contact")}
              </a>
            </div>
          </header>
        </div>
      </div>

      <main>
        <section className="shell landing-hero">
          <p className="eyebrow">{t("eyebrow")}</p>
          <h1 className="hero-title landing-title">
            {t("titleLead")} <span className="hero-accent">{t("titleAccent")}</span>
          </h1>
          <p className="landing-lead">{t("lead")}</p>
          <div className="landing-ctas">
            <a href={contact} {...external} className="btn-primary landing-cta">
              <SendIcon size={17} />
              {t("ctaPrimary")}
            </a>
            <a href={EXAMPLE_URL} target="_blank" rel="noreferrer" className="btn-ghost landing-cta">
              {t("ctaExample")}
            </a>
          </div>
          <p className="landing-note">{t("exampleNote")}</p>
        </section>

        <section className="shell landing-section">
          <p className="eyebrow">{t("readersEyebrow")}</p>
          <h2 className="landing-h2">
            {t("readersLead")} <span className="hero-accent">{t("readersAccent")}</span>
          </h2>
          <ul className="landing-grid">
            {readers.map(({ icon: Icon, title, body }) => (
              <li key={title} className="card landing-card">
                <span className="landing-icon" aria-hidden>
                  <Icon size={20} />
                </span>
                <h3>{title}</h3>
                <p>{body}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="shell landing-section">
          <p className="eyebrow">{t("studioEyebrow")}</p>
          <h2 className="landing-h2">
            {t("studioLead")} <span className="hero-accent">{t("studioAccent")}</span>
          </h2>
          <ul className="landing-grid landing-grid-4">
            {studio.map(({ icon: Icon, title, body }) => (
              <li key={title} className="card landing-card">
                <span className="landing-icon landing-icon-sky" aria-hidden>
                  <Icon size={20} />
                </span>
                <h3>{title}</h3>
                <p>{body}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="shell landing-section">
          <p className="eyebrow">{t("stepsEyebrow")}</p>
          <h2 className="landing-h2">
            {t("stepsLead")} <span className="hero-accent">{t("stepsAccent")}</span>
          </h2>
          <ol className="landing-steps">
            {steps.map((s, i) => (
              <li key={s.title}>
                <span className="landing-step-no">{i + 1}</span>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="contact" className="shell landing-section">
          <div className="landing-final">
            <h2 className="landing-h2">
              {t("finalLead")} <span className="hero-accent">{t("finalAccent")}</span>
            </h2>
            <p>{t("finalBody")}</p>
            <a href={contact} {...external} className="btn-primary landing-cta">
              <SendIcon size={17} />
              {t("telegram")}
            </a>
          </div>
        </section>
      </main>

      <footer className="mt-16 border-t">
        <div className="shell flex flex-wrap items-center gap-x-5 gap-y-2 py-6 text-xs text-muted-foreground">
          <span>© Osor</span>
          <a href={EXAMPLE_URL} className="link-quiet" target="_blank" rel="noreferrer">
            the-bakiroo.uz
          </a>
          <span className="ml-auto">{common("madeBy")}</span>
        </div>
      </footer>
    </div>
  );
}
