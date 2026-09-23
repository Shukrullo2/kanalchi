/**
 * Laying words out as a cloud.
 *
 * The classic spiral packing: take the words largest first, walk an Archimedean
 * spiral out from the centre, and drop each one at the first place it does not
 * touch anything already down. Big words end up in the middle, small ones fill
 * the gaps around them, and the result is dense without ever overlapping.
 *
 * Two decisions worth naming, because they are what keep this a server
 * component with no layout flash and no dependency:
 *
 * Widths are estimated from the characters rather than measured, since there is
 * no canvas to measure with on the server. A per-character table (an `i` is not
 * a `W`) gets close enough that a little padding hides the error, and being
 * arithmetic it gives the same answer on the server and in the browser.
 *
 * Collisions go through a coarse grid. Checking each candidate position against
 * every word already placed is O(n^2) per spiral step and far too slow for a
 * few hundred words on every request; bucketing by cell makes it near constant.
 */

export type CloudInput = {
  key: string;
  text: string;
  /** 0..1, how much of the group this word accounts for. Drives size. */
  weight: number;
  href: string;
  tier: string;
  title: string;
};

/** Where a word ended up. Carried alongside whatever the caller put in. */
export type Placement = {
  /** Centre of the word, which is also what it rotates about. */
  cx: number;
  cy: number;
  size: number;
  rotated: boolean;
};

export type PlacedWord = CloudInput & Placement;

export type CloudLayout<T = CloudInput> = {
  words: (T & Placement)[];
  viewBox: string;
  /** Width and height in the same units as the viewBox, for the aspect ratio. */
  width: number;
  height: number;
  /** Top-left of the box, so a caller can express a word's position as a share of it. */
  minX: number;
  minY: number;
};

// Narrow and wide characters, as fractions of the font size. Everything else
// falls into the two default buckets below.
const NARROW = new Set("ijltfrIJ1.,:;'’ʻ‘!|()[]{}-");
const WIDE = new Set("mwMW@%—");

function charWidth(ch: string): number {
  if (ch === " ") return 0.26;
  if (NARROW.has(ch)) return 0.33;
  if (WIDE.has(ch)) return 0.86;
  // A capital is appreciably wider than a lower-case letter in every face we
  // use, and these names are full of them.
  if (ch !== ch.toLowerCase() && ch === ch.toUpperCase()) return 0.68;
  return 0.55;
}

function textWidth(text: string, size: number): number {
  let units = 0;
  for (const ch of text) units += charWidth(ch);
  return units * size;
}

/** A stable pseudo-random number for a key, so a word rotates the same way on every render. */
function hash(key: string): number {
  let h = 2166136261;
  for (let i = 0; i < key.length; i += 1) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) / 4294967295;
}

type Rect = { x: number; y: number; w: number; h: number };

/** Bucketed rectangles, so a collision test only looks at its own neighbourhood. */
class Grid {
  private readonly cell: number;
  private readonly buckets = new Map<string, Rect[]>();

  constructor(cell: number) {
    this.cell = cell;
  }

  private *keys(r: Rect): Generator<string> {
    const x0 = Math.floor(r.x / this.cell);
    const x1 = Math.floor((r.x + r.w) / this.cell);
    const y0 = Math.floor(r.y / this.cell);
    const y1 = Math.floor((r.y + r.h) / this.cell);
    for (let x = x0; x <= x1; x += 1) {
      for (let y = y0; y <= y1; y += 1) yield `${x},${y}`;
    }
  }

  hits(r: Rect): boolean {
    for (const key of this.keys(r)) {
      const bucket = this.buckets.get(key);
      if (!bucket) continue;
      for (const other of bucket) {
        if (
          r.x < other.x + other.w &&
          r.x + r.w > other.x &&
          r.y < other.y + other.h &&
          r.y + r.h > other.y
        ) {
          return true;
        }
      }
    }
    return false;
  }

  add(r: Rect): void {
    for (const key of this.keys(r)) {
      const bucket = this.buckets.get(key);
      if (bucket) bucket.push(r);
      else this.buckets.set(key, [r]);
    }
  }
}

export type CloudOptions = {
  minSize: number;
  maxSize: number;
  /** How much wider than tall to aim for; the spiral is stretched by this. */
  aspect: number;
  /** Share of words turned on their side, 0..1. */
  rotateShare: number;
};

export function layoutCloud<T extends CloudInput>(
  input: T[],
  options: CloudOptions,
): CloudLayout<T> {
  const { minSize, maxSize, aspect, rotateShare } = options;
  // Largest first: the big words must get the middle, or they end up marooned
  // at the edge with a hole where they should have been.
  const ordered = [...input].sort((a, b) => b.weight - a.weight);

  const grid = new Grid(Math.max(24, minSize * 2));
  const placed: (T & Placement)[] = [];
  let minX = 0;
  let maxX = 0;
  let minY = 0;
  let maxY = 0;

  for (const word of ordered) {
    const size = minSize + (maxSize - minSize) * word.weight;
    const rotated = hash(word.key) < rotateShare;
    // A word's box is its text turned on its side, plus a little air so that
    // neighbours do not appear to touch.
    const long = textWidth(word.text, size) + size * 0.34;
    const short = size * 1.24;
    const w = rotated ? short : long;
    const h = rotated ? long : short;

    let angle = 0.1;
    let done = false;
    while (!done && angle < 900) {
      const radius = 2.6 * angle;
      const cx = radius * Math.cos(angle) * aspect;
      const cy = radius * Math.sin(angle);
      const rect: Rect = { x: cx - w / 2, y: cy - h / 2, w, h };
      if (!grid.hits(rect)) {
        grid.add(rect);
        placed.push({ ...word, cx, cy, size, rotated });
        minX = Math.min(minX, rect.x);
        maxX = Math.max(maxX, rect.x + w);
        minY = Math.min(minY, rect.y);
        maxY = Math.max(maxY, rect.y + h);
        done = true;
      }
      // Step by a constant arc length rather than a constant angle, so the
      // spiral does not stride over usable gaps once it gets wide.
      angle += Math.max(0.03, 5 / Math.max(radius, 1));
    }
  }

  const pad = maxSize * 0.2;
  const width = maxX - minX + pad * 2;
  const height = maxY - minY + pad * 2;
  return {
    words: placed,
    viewBox: `${minX - pad} ${minY - pad} ${width} ${height}`,
    width,
    height,
    minX: minX - pad,
    minY: minY - pad,
  };
}
