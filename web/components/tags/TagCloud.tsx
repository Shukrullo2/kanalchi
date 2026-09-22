import Link from "next/link";
import { tierOf } from "@/lib/dimensions";
import { tagLabel } from "@/lib/labels";
import type { TagOut } from "@/lib/types";
import { type CloudInput, type CloudLayout, layoutCloud } from "@/lib/wordcloud";

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
 * The whole thing is laid out on the server and shipped as SVG: real links a
 * crawler can follow, no layout flash, and nothing to run in the browser.
 */

// Two clouds, because one cannot serve both widths, and they are not the same
// kind of cloud.
//
// A packed cloud is laid out once and then scaled by the page to fit, so the
// narrower the screen the smaller every word. On a phone that is fatal: the
// widest name here is "Uzsanoatqurilishbank (SQB)", and twenty-six characters
// across 343 pixels caps the largest word at about 22px however it is laid out.
// Whatever ratio the cloud then wants puts the smallest word into single
// figures.
//
// So phones get the older kind of tag cloud: words set in a line, at varying
// sizes, wrapping as text does. It reflows to any width, every word stays
// legible, and it is no less a cloud for having no gaps to pack.
const PACKED = { minSize: 40, maxSize: 130, aspect: 1.9, rotateShare: 0, words: 48 };
const FLOW_WORDS = 40;
const FLOW_MIN_REM = 0.8125;
const FLOW_MAX_REM = 1.375;

function weigh(tags: TagOut[], locale: string, limit: number): CloudInput[] {
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
    title: `${tagLabel(tag, locale)} — ${tag.post_count}`,
  }));
}

function Cloud({ layout, className }: { layout: CloudLayout; className: string }) {
  return (
    <svg
      className={className}
      viewBox={layout.viewBox}
      role="list"
      aria-label="Tags"
      preserveAspectRatio="xMidYMid meet"
    >
      {layout.words.map((word) => (
        <Link
          key={word.key}
          href={word.href}
          className="cloud-word"
          data-tier={word.tier}
          role="listitem"
          aria-label={word.title}
          style={{ "--w": word.weight.toFixed(3) } as React.CSSProperties}
        >
          <title>{word.title}</title>
          <text
            x={word.cx}
            y={word.cy}
            fontSize={word.size}
            textAnchor="middle"
            dominantBaseline="central"
          >
            {word.text}
          </text>
        </Link>
      ))}
    </svg>
  );
}

function FlowCloud({ words }: { words: CloudInput[] }) {
  return (
    <div className="tag-cloud-flow" role="list" aria-label="Tags">
      {words.map((word) => (
        <Link
          key={word.key}
          href={word.href}
          className="flow-word"
          data-tier={word.tier}
          role="listitem"
          aria-label={word.title}
          title={word.title}
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
  );
}

export function TagCloud({ tags, locale }: { tags: TagOut[]; locale: string }) {
  if (tags.length === 0) return null;
  const packed = layoutCloud(weigh(tags, locale, PACKED.words), PACKED);

  return (
    <>
      <Cloud layout={packed} className="tag-cloud tag-cloud-packed" />
      {/* The phone's copy is hidden from assistive technology: it is the same
          links again, and a screen reader should not read the group twice. */}
      <div className="tag-cloud-small" aria-hidden>
        <FlowCloud words={weigh(tags, locale, FLOW_WORDS)} />
      </div>
    </>
  );
}
