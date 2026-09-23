/**
 * Turning a window of posts into something a force layout can draw.
 *
 * Two shapes come out of the same payload. The constellation is every post as a
 * dot and every subject as a hub, with a post tied to its subjects, to the post
 * it answered and to the posts it cites. The tag map drops the posts and ties
 * two subjects together when they were used on the same post, as often as that
 * happened. Both are pure functions of the posts and the filters, so they can
 * be recomputed on every keystroke without touching the canvas.
 */

import type { GraphOut, GraphPost, GraphTag } from "./types";

export type Mode = "constellation" | "tags";

export type GNode = {
  id: string;
  kind: "post" | "tag";
  /** Radius in graph units. */
  r: number;
  /** 0 for the most-used subject; decides which labels survive at a distance. */
  rank: number;
  deg: number;
  post?: GraphPost;
  tag?: GraphTag;
  nb: Set<GNode>;
  x: number;
  y: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
  index?: number;
};

export type GLink = {
  source: GNode;
  target: GNode;
  /** post→subject, post→post (reply or citation), or subject↔subject (used together). */
  kind: "tag" | "post" | "co";
  w: number;
};

export type Graph = { nodes: GNode[]; links: GLink[]; wmax: number };

export type Filters = {
  q: string;
  /** Selected subject slugs; a post stays when it carries any of them. */
  tags: Set<string>;
  /** Dimensions whose subjects are drawn. */
  dims: Set<string>;
};

export const CAPS = { tagNodes: 140, postNodes: 2600, mapNodes: 110, mapEdges: 420 };

/** Posts that pass the search and the subject filter. Dimensions do not remove posts, only hubs. */
export function filterPosts(data: GraphOut, f: Filters, tagText: string[]): GraphPost[] {
  const q = f.q.trim().toLowerCase();
  const wanted = f.tags.size ? new Set([...f.tags].map((s) => data.tags.findIndex((t) => t.slug === s))) : null;
  return data.posts.filter((p) => {
    if (wanted && !p.tags.some((i) => wanted.has(i))) return false;
    if (!q) return true;
    return p.title.toLowerCase().includes(q) || p.tags.some((i) => tagText[i].includes(q));
  });
}

/** How often each subject (by index) is used among these posts, within the dimensions switched on. */
export function tagUse(posts: GraphPost[], data: GraphOut, dims: Set<string>): Map<number, number> {
  const use = new Map<number, number>();
  for (const p of posts) {
    for (const i of p.tags) {
      if (!dims.has(data.tags[i].dimension ?? "")) continue;
      use.set(i, (use.get(i) ?? 0) + 1);
    }
  }
  return use;
}

function postRadius(p: GraphPost): number {
  return 2 + Math.log10(p.views + 1) * 0.7;
}

function tagNode(tag: GraphTag, count: number, rank: number, scale: number): GNode {
  return {
    id: `t:${tag.slug}`,
    kind: "tag",
    tag: { ...tag, count },
    r: 4 + Math.sqrt(count) * scale,
    rank,
    deg: 0,
    nb: new Set(),
    x: 0,
    y: 0,
  };
}

function connect(links: GLink[]) {
  for (const l of links) {
    l.source.nb.add(l.target);
    l.target.nb.add(l.source);
  }
}

export function buildConstellation(posts: GraphPost[], data: GraphOut, use: Map<number, number>): Graph {
  const hubs = [...use.entries()]
    .filter(([, n]) => n >= 2)
    .sort((a, b) => b[1] - a[1] || a[0] - b[0])
    .slice(0, CAPS.tagNodes);
  const tagByIndex = new Map<number, GNode>(hubs.map(([i, n], rank) => [i, tagNode(data.tags[i], n, rank, 1.5)]));
  const postNodes: GNode[] = posts.slice(0, CAPS.postNodes).map((p) => ({
    id: `p:${p.id}`,
    kind: "post",
    post: p,
    r: postRadius(p),
    rank: 0,
    deg: 0,
    nb: new Set(),
    x: 0,
    y: 0,
  }));
  const postById = new Map(postNodes.map((n) => [n.post!.id, n]));
  const links: GLink[] = [];
  for (const n of postNodes) {
    const p = n.post!;
    for (const i of p.tags) {
      const hub = tagByIndex.get(i);
      if (!hub) continue;
      links.push({ source: n, target: hub, kind: "tag", w: 1 });
      n.deg++;
      hub.deg++;
    }
    if (p.reply !== null) {
      const other = postById.get(p.reply);
      if (other) links.push({ source: n, target: other, kind: "post", w: 1 });
    }
    for (const id of p.links) {
      const other = postById.get(id);
      if (other && other !== n) links.push({ source: n, target: other, kind: "post", w: 1 });
    }
  }
  connect(links);
  return { nodes: [...tagByIndex.values(), ...postNodes], links, wmax: 1 };
}

export function buildTagMap(posts: GraphPost[], data: GraphOut, use: Map<number, number>): Graph {
  const top = [...use.entries()]
    .filter(([, n]) => n >= 2)
    .sort((a, b) => b[1] - a[1] || a[0] - b[0])
    .slice(0, CAPS.mapNodes);
  const byIndex = new Map<number, GNode>(top.map(([i, n], rank) => [i, tagNode(data.tags[i], n, rank, 2.2)]));
  const pairs = new Map<string, number>();
  for (const p of posts) {
    const ts = p.tags.filter((i) => byIndex.has(i));
    for (let a = 0; a < ts.length; a++) {
      for (let b = a + 1; b < ts.length; b++) {
        const key = `${ts[a]}|${ts[b]}`;
        pairs.set(key, (pairs.get(key) ?? 0) + 1);
      }
    }
  }
  const links: GLink[] = [...pairs.entries()]
    .filter(([, w]) => w >= 2)
    .sort((a, b) => b[1] - a[1])
    .slice(0, CAPS.mapEdges)
    .map(([key, w]) => {
      const [a, b] = key.split("|").map(Number);
      return { source: byIndex.get(a)!, target: byIndex.get(b)!, kind: "co" as const, w };
    });
  connect(links);
  for (const l of links) {
    l.source.deg++;
    l.target.deg++;
  }
  return { nodes: [...byIndex.values()], links, wmax: Math.max(1, ...links.map((l) => l.w)) };
}

/** Dimensions that occur in the window, most-used first within each tier. */
export function dimensionsIn(data: GraphOut, rank: (dimension: string) => number): { key: string; tags: number }[] {
  const counts = new Map<string, number>();
  for (const t of data.tags) {
    const key = t.dimension ?? "";
    if (!key) continue;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([key, tags]) => ({ key, tags }))
    .sort((a, b) => rank(a.key) - rank(b.key) || b.tags - a.tags);
}

/** `2026-06-24` → the same day as a UTC timestamp, for scales and comparisons. */
export function dayMs(iso: string): number {
  return Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
}

export function isoDay(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}
