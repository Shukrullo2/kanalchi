/**
 * Compact numbers written by hand, for the same reason as the month names: `Intl` compact notation
 * disagrees between runtimes for Uzbek ("20,7 ming" on the server, "20.7K" in the browser), which
 * breaks hydration. K/M/B read the same in all three of our locales.
 */
export function compactNumber(n: number): string {
  const abs = Math.abs(n);
  if (abs < 1000) return String(n);
  const units: [number, string][] = [
    [1_000_000_000, "B"],
    [1_000_000, "M"],
    [1000, "K"],
  ];
  for (const [size, suffix] of units) {
    if (abs >= size) {
      const value = n / size;
      const rounded = Math.abs(value) < 10 ? Math.round(value * 10) / 10 : Math.round(value);
      return `${rounded}${suffix}`;
    }
  }
  return String(n);
}

/**
 * Month names are spelled out here rather than taken from `Intl`.
 *
 * Browser ICU data for Uzbek is patchy: the same call that gives "21-sen" on the server can give
 * "M09 21" in a browser, which both looks wrong and breaks hydration. Three locales, twelve names
 * each, is a small price for output that is identical everywhere.
 */
const MONTHS: Record<string, string[]> = {
  uz: ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"],
  ru: ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
  en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
};

const MONTHS_LONG: Record<string, string[]> = {
  uz: ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"],
  ru: ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"],
  en: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
};

function months(locale: string, long = false): string[] {
  const table = long ? MONTHS_LONG : MONTHS;
  return table[locale] ?? table[locale.split("-")[0]] ?? table.en;
}

/**
 * Absolute dates, not "3 hours ago": in a news archive the date is the information, and a relative
 * label depends on the current time, which differs between the server render and the browser.
 */
export function postDate(iso: string, locale = "en"): string {
  const date = new Date(iso);
  const day = date.getDate();
  const month = months(locale)[date.getMonth()];
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return sameYear ? `${day} ${month}` : `${day} ${month} ${date.getFullYear()}`;
}

export function fullDate(iso: string, locale = "en"): string {
  const d = new Date(iso);
  const time = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  return `${d.getDate()} ${months(locale, true)[d.getMonth()]} ${d.getFullYear()}, ${time}`;
}

export function monthLabel(month: string, locale = "en"): string {
  const [y, m] = month.split("-").map(Number);
  if (!y || !m) return month;
  return `${months(locale)[m - 1]} ${String(y).slice(2)}`;
}

/** The month a post belongs to, for grouping the register into runs. */
export function monthKey(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/**
 * "sentabr 2026" — the marker that separates one run of entries from the next.
 *
 * Russian needs its own table here: the long month names above are genitive
 * because they are written for "21 сентября 2026", and a month standing on its
 * own takes the nominative.
 */
const RU_MONTHS_NOM = [
  "январь", "февраль", "март", "апрель", "май", "июнь",
  "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
];

export function monthTitle(iso: string, locale = "en"): string {
  const d = new Date(iso);
  const base = locale.split("-")[0];
  const name = base === "ru" ? RU_MONTHS_NOM[d.getMonth()] : months(locale, true)[d.getMonth()];
  return `${name} ${d.getFullYear()}`;
}

/** The span an archive covers, written as "sen 2024 — sen 2026". */
export function dateSpan(first: string, last: string, locale = "en"): string {
  const a = new Date(first);
  const b = new Date(last);
  const left = `${months(locale)[a.getMonth()]} ${a.getFullYear()}`;
  const right = `${months(locale)[b.getMonth()]} ${b.getFullYear()}`;
  return left === right ? left : `${left} — ${right}`;
}

/**
 * A channel with no photo gets a flat tone from the palette rather than a generated
 * gradient: two initials on one of four inks, picked deterministically from the name.
 */
export function initialsTone(seed: string): { initials: string; style: React.CSSProperties } {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) % 4;
  const tones = [
    "oklch(0.505 0.178 268)",
    "oklch(0.545 0.163 27)",
    "oklch(0.44 0.09 230)",
    "oklch(0.42 0.07 285)",
  ];
  const initials = seed
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
  return { initials: initials || "K", style: { background: tones[hash] } };
}
