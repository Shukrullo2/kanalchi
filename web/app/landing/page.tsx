import type { Metadata } from "next";
import Image from "next/image";
import { getTranslations } from "next-intl/server";
import {
  ArrowRightIcon,
  CalendarIcon,
  ChartIcon,
  ChatIcon,
  ExternalIcon,
  GlobeIcon,
  IdeaIcon,
  MapIcon,
  PenIcon,
  SearchIcon,
  SendIcon,
  TagIcon,
} from "@/components/Icons";
import {
  EXAMPLE_HOST,
  EXAMPLE_URL,
  LandingShell,
} from "@/components/landing/LandingShell";
import { PlanCards } from "@/components/signup/PlanCards";
import { apiFetchOrNull } from "@/lib/api";
import { CONTACT_URL } from "@/lib/config";
import type { PlanCatalogue } from "@/lib/types";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("landing");
  return {
    title: { absolute: t("metaTitle") },
    description: t("metaDescription"),
  };
}

type Feature = {
  icon: typeof GlobeIcon;
  title: string;
  body: string;
  /** Path on the example channel this feature lives at; also names the screenshot. */
  path: string;
  shot: string;
};

/**
 * osor.uz: what the service does, for the people who read a channel and for the
 * person who writes it, what it costs, and the way in. Every feature card is a
 * screenshot of the example channel and opens that very page. Every button that
 * asks for something leads to /start, where a blogger signs in with Telegram and
 * adds their channel; the owner's Telegram stays as the place for questions.
 */
export default async function Landing() {
  const [t, catalogue] = await Promise.all([
    getTranslations("landing"),
    apiFetchOrNull<PlanCatalogue>("/api/signup/plans"),
  ]);

  const readers: Feature[] = [
    {
      icon: GlobeIcon,
      title: t("f1t"),
      body: t("f1b"),
      path: "/posts",
      shot: "posts",
    },
    {
      icon: TagIcon,
      title: t("f2t"),
      body: t("f2b"),
      path: "/tags",
      shot: "tags",
    },
    {
      icon: SearchIcon,
      title: t("f3t"),
      body: t("f3b"),
      path: "/search?q=Toshkent",
      shot: "search",
    },
    {
      icon: ChatIcon,
      title: t("f4t"),
      body: t("f4b"),
      path: "/chat",
      shot: "chat",
    },
    {
      icon: MapIcon,
      title: t("f5t"),
      body: t("f5b"),
      path: "/graph",
      shot: "graph",
    },
    {
      icon: ChartIcon,
      title: t("f6t"),
      body: t("f6b"),
      path: "/",
      shot: "stats",
    },
  ];
  const studio: Feature[] = [
    {
      icon: IdeaIcon,
      title: t("s1t"),
      body: t("s1b"),
      path: "/studio/ideas",
      shot: "studio-ideas",
    },
    {
      icon: PenIcon,
      title: t("s2t"),
      body: t("s2b"),
      path: "/studio/drafts",
      shot: "studio-drafts",
    },
    {
      icon: SearchIcon,
      title: t("s3t"),
      body: t("s3b"),
      path: "/studio/research",
      shot: "studio-research",
    },
    {
      icon: CalendarIcon,
      title: t("s4t"),
      body: t("s4b"),
      path: "/studio",
      shot: "studio",
    },
  ];
  const steps = [
    { title: t("p1t"), body: t("p1b") },
    { title: t("p2t"), body: t("p2b") },
    { title: t("p3t"), body: t("p3b") },
  ];
  const telegram = [t("bookTg1"), t("bookTg2"), t("bookTg3"), t("bookTg4")];
  const osor = [t("bookOsor1"), t("bookOsor2"), t("bookOsor3"), t("bookOsor4")];

  const featureCard = (
    { icon: Icon, title, body, path, shot }: Feature,
    tone?: "sky",
  ) => (
    <li key={path}>
      <a
        href={`${EXAMPLE_URL}${path}`}
        target="_blank"
        rel="noreferrer"
        className="card landing-card landing-shot-card"
      >
        <figure className="landing-shot">
          <Image
            src={`/landing/${shot}.webp`}
            alt={title}
            width={1600}
            height={900}
            loading="lazy"
          />
        </figure>
        <div className="landing-shot-body">
          <span
            className={
              tone === "sky" ? "landing-icon landing-icon-sky" : "landing-icon"
            }
            aria-hidden
          >
            <Icon size={20} />
          </span>
          <h3>{title}</h3>
          <p>{body}</p>
          <span className="landing-shot-link">
            <span className="landing-shot-hint">{t("shotHint")}</span>
            <span className="landing-shot-url">
              {EXAMPLE_HOST}
              {path === "/" ? "" : path}
              <ExternalIcon size={13} />
            </span>
          </span>
        </div>
      </a>
    </li>
  );

  return (
    <LandingShell>
      <section className="shell landing-hero">
        <p className="eyebrow">{t("eyebrow")}</p>
        <h1 className="hero-title landing-title">
          {t("titleLead")}{" "}
          <span className="hero-accent">{t("titleAccent")}</span>
        </h1>
        <p className="landing-lead">{t("lead")}</p>
        <div className="landing-ctas">
          <a href="/start" className="btn-primary landing-cta">
            {t("ctaPrimary")}
            <ArrowRightIcon size={17} />
          </a>
          <a
            href={EXAMPLE_URL}
            target="_blank"
            rel="noreferrer"
            className="btn-ghost landing-cta"
          >
            {t("ctaExample")}
          </a>
        </div>
        <p className="landing-note">{t("exampleNote")}</p>
      </section>

      <section className="shell landing-section">
        <p className="eyebrow">{t("bookEyebrow")}</p>
        <h2 className="landing-h2">
          {t("bookLead")} <span className="hero-accent">{t("bookAccent")}</span>
        </h2>
        <p className="landing-lead">{t("bookBody")}</p>
        <div className="landing-compare">
          <div className="landing-compare-col landing-compare-tg">
            <h3>
              <span className="landing-compare-badge" aria-hidden>
                <SendIcon size={15} />
              </span>
              {t("bookTgTitle")}
            </h3>
            <ul>
              {telegram.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
          <div className="landing-compare-col landing-compare-osor">
            <h3>
              <span className="landing-mark" aria-hidden>
                O
              </span>
              {t("bookOsorTitle")}
            </h3>
            <ul>
              {osor.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="shell landing-section">
        <p className="eyebrow">{t("readersEyebrow")}</p>
        <h2 className="landing-h2">
          {t("readersLead")}{" "}
          <span className="hero-accent">{t("readersAccent")}</span>
        </h2>
        <ul className="landing-grid landing-grid-shots">
          {readers.map((f) => featureCard(f))}
        </ul>
      </section>

      <section className="shell landing-section">
        <p className="eyebrow">{t("studioEyebrow")}</p>
        <h2 className="landing-h2">
          {t("studioLead")}{" "}
          <span className="hero-accent">{t("studioAccent")}</span>
        </h2>
        <ul className="landing-grid landing-grid-shots">
          {studio.map((f) => featureCard(f, "sky"))}
        </ul>
        <p className="landing-note">{t("studioNote")}</p>
      </section>

      {catalogue ? (
        <section id="pricing" className="shell landing-section">
          <p className="eyebrow">{t("pricingEyebrow")}</p>
          <h2 className="landing-h2">
            {t("pricingLead")}{" "}
            <span className="hero-accent">{t("pricingAccent")}</span>
          </h2>
          <p className="landing-lead">
            {t("pricingBody", {
              posts: catalogue.onboarding.sample.posts.toLocaleString("en-US"),
              price: catalogue.onboarding.sample.price_usd,
            })}
          </p>
          <div className="mt-8">
            <PlanCards plans={catalogue.plans} />
          </div>
          <a href="/start" className="btn-primary landing-cta mt-6">
            {t("pricingCta")}
            <ArrowRightIcon size={17} />
          </a>
        </section>
      ) : null}

      <section className="shell landing-section">
        <p className="eyebrow">{t("stepsEyebrow")}</p>
        <h2 className="landing-h2">
          {t("stepsLead")}{" "}
          <span className="hero-accent">{t("stepsAccent")}</span>
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
            {t("finalLead")}{" "}
            <span className="hero-accent">{t("finalAccent")}</span>
          </h2>
          <p>{t("finalBody")}</p>
          <div className="landing-ctas mt-0">
            <a href="/start" className="btn-primary landing-cta">
              {t("ctaPrimary")}
              <ArrowRightIcon size={17} />
            </a>
            {CONTACT_URL ? (
              <a
                href={CONTACT_URL}
                target="_blank"
                rel="noreferrer"
                className="btn-ghost landing-cta"
              >
                <SendIcon size={16} />
                {t("finalContact")}
              </a>
            ) : null}
          </div>
        </div>
      </section>
    </LandingShell>
  );
}
