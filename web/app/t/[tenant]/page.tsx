import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import { AreaChart } from "@/components/stats/AreaChart";
import { Bars } from "@/components/stats/Bars";
import { CalendarHeatmap } from "@/components/stats/CalendarHeatmap";
import { MatrixHeatmap } from "@/components/stats/MatrixHeatmap";
import { ProportionBar, RankedBars } from "@/components/stats/Ranked";
import { TagChip } from "@/components/tags/TagChip";
import { apiFetch } from "@/lib/api";
import { compactNumber, dateSpan, monthLabel } from "@/lib/format";
import { tagLabel } from "@/lib/labels";
import type { ChannelStats, StatTag, TenantPublic } from "@/lib/types";

export async function generateMetadata(): Promise<Metadata> {
  const tenant = await apiFetch<TenantPublic>("/api/tenant");
  return {
    title: tenant.title || tenant.domain,
    description: tenant.about ?? undefined,
    alternates: { types: { "application/rss+xml": "/feed.xml" } },
    openGraph: { title: tenant.title, description: tenant.about ?? undefined, type: "website" },
  };
}

/** Endonyms: a language is written in its own name, whatever page you are on. */
const LANGUAGE_NAMES: Record<string, string> = {
  "uz-latn": "O‘zbek (lotin)",
  "uz-cyrl": "Ўзбек (кирилл)",
  ru: "Русский",
  en: "English",
};

/** A Telegram bio is often a list of "Label: url" pairs; drop the URLs and any label left dangling. */
function cleanAbout(about: string): string {
  return about
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\S+:\s*(?=\S+:|$)/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/** "Bakiroo arxivi" → the last word in gold, so the headline has a second colour. */
function splitTitle(title: string): [string, string] {
  const words = title.trim().split(/\s+/);
  if (words.length < 2) return [title, ""];
  return [words.slice(0, -1).join(" ") + " ", words[words.length - 1]];
}

/**
 * The front page: who this channel is, then what it turns out to be about, then
 * how it posts.
 *
 * The order is the argument. What the archive knows — the subjects, the names,
 * the bodies it covers — comes from having read every post, and is the one
 * thing a follower-count service cannot show; it goes directly under the
 * headline numbers. The posting rhythm is real but ordinary, so the calendar
 * and the weekday charts sit below it rather than opening the page.
 */
export default async function TenantHome() {
  const [tenant, stats, locale, t, h] = await Promise.all([
    apiFetch<TenantPublic>("/api/tenant"),
    apiFetch<ChannelStats>("/api/stats"),
    getLocale(),
    getTranslations("stats"),
    getTranslations("home"),
  ]);

  const title = tenant.title || tenant.domain;
  const [head, tail] = splitTitle(title);
  const span =
    tenant.first_post_at && tenant.last_post_at
      ? dateSpan(tenant.first_post_at, tenant.last_post_at, locale)
      : null;

  const firstYear = stats.first_post_at ? new Date(stats.first_post_at).getFullYear() : null;
  const lastYear = stats.last_post_at ? new Date(stats.last_post_at).getFullYear() : firstYear;
  const years =
    firstYear && lastYear ? Array.from({ length: lastYear - firstYear + 1 }, (_, i) => firstYear + i) : [];
  const weekdays = [1, 2, 3, 4, 5, 6, 7].map((d) => t(`d${d}` as "d1"));
  const months = Array.from({ length: 12 }, (_, m) =>
    monthLabel(`2000-${String(m + 1).padStart(2, "0")}`, locale).split(" ")[0],
  );
  // Raw ICU strings go to the client charts, which fill them in; functions cannot cross that boundary.
  const postsTpl = t.raw("busiestUnit") as string;
  const posts = (n: number) => postsTpl.replace("{count}", String(n));
  const postsValueTpl = postsTpl.replace("{count}", "{value}");
  const linksTpl = t.raw("links") as string;
  const matrixTpl = t.raw("matrixCaption") as string;

  const weekdayRows = [1, 2, 3, 4, 5, 6, 7].map(
    (d) => stats.by_weekday.find((r) => r.dow === d) ?? { dow: d, posts: 0, mean_views: 0 },
  );
  const hours = Array.from({ length: 24 }, (_, h) => String(h));
  const label = (tag: StatTag) => tagLabel({ name: tag.name, labels: tag.labels }, locale);

  const kpis: [string, string][] = [
    [t("posts"), compactNumber(stats.posts)],
    [t("views"), compactNumber(stats.total_views)],
    [t("viewsPerPost"), compactNumber(stats.mean_views)],
    [t("forwards"), compactNumber(stats.total_forwards)],
    [t("years"), years.length ? `${years[0]}–${years[years.length - 1]}` : "—"],
    [t("streak"), t("streakUnit", { count: stats.longest_streak_days })],
    [
      t("busiest"),
      stats.busiest_day
        ? `${stats.busiest_day.day.replace(/-/g, "‑")} · ${posts(stats.busiest_day.posts)}`
        : "—",
    ],
    [
      t("mediaMix"),
      stats.media_mix[0]
        ? `${Math.round((stats.media_mix[0].posts / Math.max(1, stats.posts)) * 100)}% ${
            t.has(stats.media_mix[0].kind as "none") ? t(stats.media_mix[0].kind as "none") : stats.media_mix[0].kind
          }`
        : "—",
    ],
  ];

  const afterIndexing = [
    ["topThemes", stats.top_themes],
    ["topPeople", stats.top_people],
    ["topGovOrgs", stats.top_gov_orgs],
    ["formats", stats.by_format],
  ] as const;

  return (
    <div>
      <header className="py-8 text-center sm:py-12">
        {tenant.username ? <p className="eyebrow">@{tenant.username}</p> : null}
        <h1 className="hero-title mt-3">
          {head}
          {tail ? <span className="hero-accent">{tail}</span> : null}
        </h1>
        {tenant.about ? (
          <p className="mx-auto mt-5 line-clamp-2 max-w-[56ch] text-pretty text-[0.9375rem] text-muted-foreground">
            {cleanAbout(tenant.about)}
          </p>
        ) : null}
        <p className="meta-row mt-4 justify-center">
          {span ? <span suppressHydrationWarning>{span}</span> : null}
          {tenant.participants_count ? (
            <span>{h("subscribers", { count: compactNumber(tenant.participants_count) })}</span>
          ) : null}
        </p>
      </header>

      <dl className="grid grid-cols-2 gap-4 border-t py-6 sm:grid-cols-4">
        {kpis.map(([k, v]) => (
          <div key={k} className="card p-4">
            <dd className="stat-value text-[1.35rem]">{v}</dd>
            <dt className="stat-label">{k}</dt>
          </div>
        ))}
      </dl>

      {/* What the archive knows. Needs the posts to have been read, not merely counted. */}
      <section className="section">
        <h2 className="!text-[1.35rem]">{t("afterIndexing")}</h2>
        <p className="-mt-2 mb-5 max-w-[62ch] text-sm text-muted-foreground">{t("afterIndexingIntro")}</p>

        {stats.indexed_posts === 0 ? (
          <p className="pending-note">
            <span aria-hidden>◷</span>
            {t("pending", { done: compactNumber(stats.indexed_posts), total: compactNumber(stats.posts) })}
          </p>
        ) : null}

        <div className="grid gap-x-10 sm:grid-cols-2">
          {afterIndexing.map(([key, rows]) => (
            <section key={key} className="section">
              <h2>{t(key)}</h2>
              {rows.length > 0 ? (
                <RankedBars rows={rows.map((r) => ({ label: label(r), value: r.posts, href: `/tag/${r.slug}` }))} />
              ) : (
                <p className="text-sm text-muted-foreground">—</p>
              )}
            </section>
          ))}
        </div>

        {stats.by_stance.length > 0 ? (
          <section className="section">
            <h2>{t("stance")}</h2>
            <ProportionBar parts={stats.by_stance.map((r) => ({ label: label(r), value: r.posts }))} />
          </section>
        ) : null}

        {stats.top_tags.length > 0 ? (
          <section className="section">
            <h2>{t("topTags")}</h2>
            <div className="flex flex-wrap gap-2">
              {stats.top_tags.map((tag) => (
                <TagChip key={tag.slug} tag={tag} locale={locale} showCount />
              ))}
            </div>
          </section>
        ) : null}
      </section>

      {/* How it posts, and how it gets read: everything a count alone can answer. */}
      <section className="section border-t pt-8">
        <h2 className="!text-[1.35rem]">{t("title")}</h2>
        <p className="-mt-2 mb-5 max-w-[62ch] text-sm text-muted-foreground">{t("intro")}</p>

        {years.length > 0 ? (
          <section className="section">
            <h2>{t("calendar")}</h2>
            <p className="-mt-2 mb-4 text-sm text-muted-foreground">{t("calendarHint")}</p>
            <CalendarHeatmap
              days={stats.by_day}
              years={years}
              initialYear={years[years.length - 1]}
              labels={{ months, weekdays, less: t("less"), more: t("more"), postsTemplate: postsTpl }}
            />
          </section>
        ) : null}

        <section className="section">
          <h2>{t("weekdayHour")}</h2>
          <p className="-mt-2 mb-4 text-sm text-muted-foreground">{t("weekdayHourHint")}</p>
          <MatrixHeatmap
            cells={stats.by_weekday_hour.map((c) => ({ row: c.dow, col: c.hour, value: c.posts }))}
            rowLabels={weekdays}
            colLabels={hours}
            legend={{ less: t("less"), more: t("more") }}
            captionTemplate={matrixTpl}
            valueTemplate={postsValueTpl}
          />
        </section>

        <div className="grid gap-x-10 sm:grid-cols-2">
          <section className="section">
            <h2>{t("byMonth")}</h2>
            <AreaChart
              data={stats.by_month.map((m) => ({ label: monthLabel(m.month, locale), value: m.posts }))}
              template={postsValueTpl}
            />
          </section>
          <section className="section">
            <h2>{t("cumulative")}</h2>
            <AreaChart
              data={stats.by_month.map((m) => ({ label: monthLabel(m.month, locale), value: m.posts }))}
              template={postsValueTpl}
              cumulative
            />
          </section>

          <section className="section">
            <h2>{t("byYear")}</h2>
            <Bars
              data={stats.by_year.map((y) => ({
                label: String(y.year),
                value: y.posts,
                hint: `${compactNumber(y.total_views)} ${t("views").toLowerCase()}`,
              }))}
              template={postsValueTpl}
            />
          </section>
          <section className="section">
            <h2>{t("readsWeekday")}</h2>
            <Bars data={weekdayRows.map((r, i) => ({ label: weekdays[i], value: r.mean_views }))} compact />
          </section>

          <section className="section">
            <h2>{t("byLength")}</h2>
            <RankedBars
              ordinal
              rows={stats.by_length.map((b) => ({
                label: t(b.bucket),
                value: b.posts,
                hint: t(`${b.bucket}Hint` as "shortHint"),
              }))}
            />
          </section>
          <section className="section">
            <h2>{t("readsLength")}</h2>
            <RankedBars
              ordinal
              rows={stats.by_length.map((b) => ({ label: t(b.bucket), value: b.mean_views }))}
              format={compactNumber}
            />
          </section>

          <section className="section">
            <h2>{t("mediaMix")}</h2>
            <ProportionBar
              parts={stats.media_mix.map((m) => ({
                label: t.has(m.kind as "photo") ? t(m.kind as "photo") : m.kind,
                value: m.posts,
              }))}
              format={compactNumber}
            />
          </section>
          {stats.by_language.length > 0 ? (
            <section className="section">
              <h2>{t("languages")}</h2>
              <ProportionBar
                parts={stats.by_language.map((l) => ({
                  label:
                    LANGUAGE_NAMES[l.language] ??
                    (t.has(l.language as "mixed") ? t(l.language as "mixed") : l.language),
                  value: l.posts,
                }))}
                format={compactNumber}
              />
            </section>
          ) : null}
        </div>

        {stats.by_domain.length > 0 ? (
          <section className="section">
            <h2>{t("sources")}</h2>
            <p className="-mt-2 mb-4 text-sm text-muted-foreground">{t("sourcesHint")}</p>
            <RankedBars
              rows={stats.by_domain.map((d) => ({
                label: d.domain,
                value: d.links,
                hint: posts(d.posts),
                href: d.telegram ? `https://t.me/${d.domain.slice(1)}` : undefined,
              }))}
              format={(v) => linksTpl.replace("{count}", compactNumber(v))}
            />
          </section>
        ) : null}
      </section>
    </div>
  );
}
