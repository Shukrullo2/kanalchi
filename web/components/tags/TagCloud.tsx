import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { dimensionTint, tierOf } from "@/lib/dimensions";
import { tagDescription, tagLabel } from "@/lib/labels";
import type { TagOut } from "@/lib/types";
import { type CloudInput, layoutCloud } from "@/lib/wordcloud";

/**
 * One group of the index, as a word cloud.
 *
 * Size is the measure, on a log scale because the counts are: the largest
 * subject in a group can have six hundred posts where the median has four, and
 * on a linear scale everything below the top few would collapse into the same
 * smallest size. Colour follows the same weight, from the group's tone at full
 * strength down to grey, so the eye lands on what matters.
 *
 * Only the most-written-about words go in. A cloud of five hundred names is
 * either unreadable or enormous, and a cloud is for the shape of a subject, not
 * for looking a particular name up — search does that.
 *
 * `lib/wordcloud.ts` places the words; this draws them as absolutely positioned
 * text, each at its share of the box, sized in `cqw` so the whole cloud scales
 * with its container. Text rather than SVG because a word then carries an
 * ordinary tooltip, can be selected, and is read by a screen reader as prose.
 */

// Two clouds, because one cannot serve both widths, and they are not the same
// kind of cloud.
//
// A packed cloud is laid out once and then scaled to fit, so the narrower the
// screen the smaller every word. On a phone that is fatal: the widest name here
// is "Uzsanoatqurilishbank (SQB)", and twenty-six characters across 343 pixels
// caps the largest word at about 22px however it is laid out. Whatever ratio
// the cloud then wants puts the smallest word into single figures.
//
// So phones get the older kind of tag cloud: words set in a line, at varying
// sizes, wrapping as text does. It reflows to any width, every word stays
// legible, and it is no less a cloud for having no gaps to pack.
const PACKED = { minSize: 40, maxSize: 130, aspect: 1.9, rotateShare: 0, words: 48 };
const FLOW_WORDS = 40;
const FLOW_MIN_REM = 0.8125;
const FLOW_MAX_REM = 1.375;

type Word = CloudInput & {
  count: number;
  description: string | null;
  /** "2019–2026", or "2019" when a subject came and went inside one year. */
  years: string | null;
  sameYear: boolean;
  /** How the tag's posts did against the channel's average, e.g. 0.93. */
  engagement: number | null;
};

/** The years a subject ran, from the span of its posts. */
function yearSpan(tag: TagOut): { years: string | null; sameYear: boolean } {
  const first = tag.first_post_at ? new Date(tag.first_post_at).getFullYear() : null;
  const last = tag.last_post_at ? new Date(tag.last_post_at).getFullYear() : null;
  if (!first || !last) return { years: null, sameYear: false };
  return { years: first === last ? `${first}` : `${first}–${last}`, sameYear: first === last };
}

function weigh(tags: TagOut[], locale: string, limit: number): Word[] {
  const top = [...tags].sort((a, b) => b.post_count - a.post_count).slice(0, limit);
  const counts = top.map((t) => Math.log(t.post_count + 1));
  const low = Math.min(...counts);
  const high = Math.max(...counts);

  return top.map((tag) => ({
    key: tag.slug,
    text: tagLabel(tag, locale),
    // Every word in the group having the same count is rare but real; give them
    // all the middle size rather than dividing by zero.
    weight: high === low ? 0.5 : (Math.log(tag.post_count + 1) - low) / (high - low),
    href: `/tag/${tag.slug}`,
    tier: tierOf(tag.dimension),
    title: tagLabel(tag, locale),
    count: tag.post_count,
    description: tagDescription(tag, locale),
    ...yearSpan(tag),
    engagement: tag.engagement_score || null,
  }));
}

/**
 * What a word says about itself on hover: what it is, and the same three
 * figures its own page opens with — how many posts, the years it ran, and how
 * it did against the channel's average.
 *
 * Not its name — the name is the word the cursor is already on, and repeating
 * it in the box above just pushes the useful part further away.
 */
function Tip({ word, labels }: { word: Word; labels: StatLabels }) {
  return (
    <span className="cloud-tip" role="tooltip" aria-hidden>
      {word.description ? <span className="cloud-tip-text">{word.description}</span> : null}
      <span className="cloud-tip-stats">
        <span className="cloud-tip-stat">
          <b>{word.count}</b> {labels.posts}
        </span>
        {word.years ? (
          <span className="cloud-tip-stat">
            <b>{word.years}</b> {word.sameYear ? labels.year : labels.years}
          </span>
        ) : null}
        {word.engagement ? (
          <span className="cloud-tip-stat">
            <b>{word.engagement}×</b> {labels.ofAverage}
          </span>
        ) : null}
      </span>
    </span>
  );
}

type StatLabels = { posts: string; year: string; years: string; ofAverage: string };

export async function TagCloud({ tags, locale }: { tags: TagOut[]; locale: string }) {
  if (tags.length === 0) return null;
  const [t, tt] = await Promise.all([getTranslations("common"), getTranslations("tag")]);
  // Every word here belongs to the same group, so the tone is the cloud's, not
  // each word's. Read off the data rather than passed in: the cloud *is* the
  // group, so there is nothing for a caller to get wrong.
  const dimension = tags[0].dimension;
  const tier = tierOf(dimension);
  const tint = dimensionTint(dimension ?? "");
  // The same short labels the tag's own page uses under its numbers.
  const labels: StatLabels = {
    posts: tt("posts"),
    year: tt("year"),
    years: tt("years"),
    ofAverage: tt("ofAverage"),
  };
  const packed = layoutCloud(weigh(tags, locale, PACKED.words), PACKED);
  const flow = weigh(tags, locale, FLOW_WORDS);

  return (
    <>
      <div
        className="tag-cloud-packed"
        data-tier={tier}
        style={
          {
            aspectRatio: `${packed.width} / ${packed.height}`,
            "--dim-tint": tint,
          } as React.CSSProperties
        }
        role="list"
        aria-label={t("tagCloud")}
      >
        {packed.words.map((word) => (
            <Link
              key={word.key}
              href={word.href}
              className="cloud-word"
              role="listitem"
              aria-label={`${word.text} — ${t("posts", { count: word.count })}`}
              style={
                {
                  "--w": word.weight.toFixed(3),
                  left: `${(((word.cx - packed.minX) / packed.width) * 100).toFixed(3)}%`,
                  top: `${(((word.cy - packed.minY) / packed.height) * 100).toFixed(3)}%`,
                  // 1cqw is one per cent of the cloud's width, so a word keeps
                  // its share of the whole however wide the page is.
                  fontSize: `${((word.size / packed.width) * 100).toFixed(3)}cqw`,
                } as React.CSSProperties
              }
            >
              <span className="cloud-word-text">{word.text}</span>
              <Tip word={word} labels={labels} />
            </Link>
          ))}
      </div>

      {/* The phone's copy is hidden from assistive technology: it is the same
          links again, and a screen reader should not read the group twice. */}
      <div className="tag-cloud-small" aria-hidden>
        <div
          className="tag-cloud-flow"
          data-tier={tier}
          style={{ "--dim-tint": tint } as React.CSSProperties}
        >
          {flow.map((word) => (
            <Link
              key={word.key}
              href={word.href}
              className="flow-word"
              title={`${word.text} — ${t("posts", { count: word.count })}`}
              style={
                {
                  "--w": word.weight.toFixed(3),
                  fontSize: `${(FLOW_MIN_REM + (FLOW_MAX_REM - FLOW_MIN_REM) * word.weight).toFixed(3)}rem`,
                } as React.CSSProperties
              }
            >
              {word.text}
            </Link>
          ))}
        </div>
      </div>
    </>
  );
}
