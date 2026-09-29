// Scene recorder: drives headless Chrome over CDP and saves JPEG frames with timestamps.
// usage: node --experimental-websocket rec.mjs <scene> [sid-cookie]
import { spawn } from "node:child_process";
import { execSync } from "node:child_process";
import { mkdirSync, writeFileSync, appendFileSync } from "node:fs";
const BACKEND = "/Users/user/Documents/blogger/backend";
const SCRATCH = new URL(".", import.meta.url).pathname; // stage.py lives next to this file

const [scene, sid] = process.argv.slice(2);
const OUT = new URL(`./scenes/${scene}/`, import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const W = 1600, H = 900, SCALE = 1.2;
const port = 9300 + Math.floor(Math.random() * 400);
const chrome = spawn(CHROME, ["--headless=new", "--hide-scrollbars", `--window-size=${W},${H}`, "--lang=uz",
  `--remote-debugging-port=${port}`, `--user-data-dir=${process.env.TMPDIR ?? "/tmp"}/rec-${port}`, "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let targets;
for (let i = 0; i < 50; i++) { try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); break; } catch { await sleep(200); } }
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map(); const listeners = new Map();
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { const { res, rej } = pending.get(m.id); pending.delete(m.id); m.error ? rej(new Error(m.error.message)) : res(m.result); }
  else if (m.method && listeners.has(m.method)) for (const cb of listeners.get(m.method)) cb(m.params);
};
const send = (method, params = {}) => new Promise((res, rej) => { pending.set(++id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
const on = (method, cb) => listeners.set(method, [...(listeners.get(method) ?? []), cb]);
await send("Page.enable"); await send("Network.enable"); await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: SCALE, mobile: false });
if (sid) await send("Network.setCookie", { name: "sid", value: sid, domain: "osor.localhost", path: "/" });
// Uzbek interface throughout, the language the product is written in.
for (const domain of ["osor.uz", "the-bakiroo.uz", "osor.localhost", "bakiroo.localhost"])
  await send("Network.setCookie", { name: "locale", value: "uz", domain, path: "/" });

// ---- frame loop -----------------------------------------------------------------------
let recording = false, n = 0; const t0 = Date.now();
async function loop() {
  while (recording) {
    try {
      // A request issued mid-navigation can go unanswered; never let it stall the loop.
      const shot = await Promise.race([
        send("Page.captureScreenshot", { format: "jpeg", quality: 85 }),
        new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), 1500)),
      ]);
      const t = Date.now() - t0; n += 1;
      const name = `f${String(n).padStart(6, "0")}.jpg`;
      writeFileSync(OUT + name, Buffer.from(shot.data, "base64"));
      appendFileSync(OUT + "times.txt", `${t} ${name}\n`);
    } catch { /* between navigations */ }
  }
}
function start() { recording = true; loop(); }
function stop() { recording = false; }

// ---- page helpers --------------------------------------------------------------------
const evaluate = async (expression) => (await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })).result.value;
async function goto(url) {
  const loaded = new Promise((r) => on("Page.loadEventFired", r));
  await send("Page.navigate", { url });
  await loaded; await sleep(300); await cursor();
}
// A visible pointer so clicks read as clicks. Fixed, above everything, moved with a CSS transition.
async function cursor() {
  await evaluate(`(() => { if (document.getElementById('__cur')) return; const d = document.createElement('div'); d.id = '__cur';
    d.innerHTML = '<svg width="26" height="30" viewBox="0 0 26 30"><path d="M3 2 L3 24 L9 18 L13 28 L17 26 L13 17 L21 17 Z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    Object.assign(d.style, { position: 'fixed', left: '0px', top: '0px', zIndex: 2147483647, pointerEvents: 'none', transition: 'transform 0.55s cubic-bezier(.2,.7,.2,1)', transform: 'translate(900px, 700px)', filter: 'drop-shadow(0 2px 4px rgba(0,0,0,.5))' });
    document.body.appendChild(d); })()`);
}
async function moveTo(selector, dx = 0, dy = 0) {
  await evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return false;
    el.scrollIntoView({ block: 'center', behavior: 'smooth' }); return true; })()`);
  await sleep(700);
  const ok = await evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return false;
    const r = el.getBoundingClientRect(); const c = document.getElementById('__cur');
    c.style.transform = 'translate(' + (r.left + r.width / 2 - 4 + ${dx}) + 'px,' + (r.top + r.height / 2 - 2 + ${dy}) + 'px)'; return true; })()`);
  if (!ok) throw new Error("no element " + selector);
  await sleep(750);
}
async function click(selector) {
  await moveTo(selector);
  // press feedback
  await evaluate(`(() => { const c = document.getElementById('__cur'); c.style.transition += ', filter 0.1s'; c.style.filter = 'drop-shadow(0 0 0 rgba(0,0,0,.5)) brightness(0.7)'; setTimeout(() => c.style.filter = 'drop-shadow(0 2px 4px rgba(0,0,0,.5))', 160); })()`);
  await sleep(120);
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).click(); true`);
}
async function clickText(text, tag = "button, a") {
  const found = await evaluate(`(() => { const els = [...document.querySelectorAll(${JSON.stringify(tag)})]; const el = els.find(e => e.textContent.trim().startsWith(${JSON.stringify(text)})); if (!el) return false; el.setAttribute('data-rec', '1'); return true; })()`);
  if (!found) throw new Error("no text " + text);
  await click("[data-rec='1']");
  await evaluate(`document.querySelectorAll('[data-rec]').forEach(e => e.removeAttribute('data-rec')); true`);
}
async function type(selector, text, delay = 70) {
  await click(selector);
  for (const ch of text) {
    await evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, el.value + ${JSON.stringify(ch)}); el.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    await sleep(delay + Math.random() * 50);
  }
}
async function scrollTo(y, settle = 1200) { await evaluate(`window.scrollTo({ top: ${y}, behavior: 'smooth' }); true`); await sleep(settle); }
async function scrollBy(dy, settle = 1200) { await evaluate(`window.scrollBy({ top: ${dy}, behavior: 'smooth' }); true`); await sleep(settle); }
async function scrollToSel(selector, settle = 1200) { await evaluate(`document.querySelector(${JSON.stringify(selector)})?.scrollIntoView({ block: 'start', behavior: 'smooth' }); true`); await sleep(settle); }
const waitFor = async (expression, ms = 30000) => { const until = Date.now() + ms; while (Date.now() < until) { if (await evaluate(`!!(${expression})`)) return true; await sleep(300); } return false; };
// Dev-only artefacts and localhost names must not appear in the demo.
async function cosmetics() {
  await evaluate(`(() => { document.querySelectorAll('nextjs-portal, [data-nextjs-toast], [data-next-badge-root]').forEach(e => e.remove());
    const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); const nodes = []; while (walk.nextNode()) nodes.push(walk.currentNode);
    for (const n of nodes) if (n.nodeValue.includes('.localhost')) n.nodeValue = n.nodeValue.replace(/\\.localhost/g, '.osor.uz'); return true; })()`);
}
const LOCAL = "http://osor.localhost:3001";
const PROD = "https://osor.uz";
const SITE = process.env.SITE_URL ?? "https://the-bakiroo.uz";

// ---- scenes --------------------------------------------------------------------------
const scenes = {
  async landing() {
    await goto(PROD + "/"); start(); await sleep(2800);
    await scrollBy(700, 2200); await scrollBy(800, 2200);           // book section
    await scrollBy(900, 2000); await scrollBy(900, 2000); await scrollBy(900, 2000); // features
    await scrollToSel("#pricing", 2600);
    await scrollBy(600, 1800);
    await clickText("Kanalim narxini", "a"); await sleep(900); stop();
  },
  async quote() {
    // The public form: type the channel, see the price, message the admin. No sign-in.
    await goto(LOCAL + "/start"); await cosmetics(); start(); await sleep(1800);
    await type("#channel-link", "@the_bakiroo", 90); await sleep(600);
    await clickText("Hisoblash", "button");
    await waitFor("document.querySelector('.signup-quote')", 30000); await cosmetics(); await sleep(3200);
    // Locally no reader account runs; stand in for its answer, and let the page's poll pick it up.
    execSync(`cd ${BACKEND} && uv run python ${SCRATCH}/stage.py finalize`, { stdio: "ignore" });
    await waitFor("document.body.innerText.includes('Telegramdan olingan')", 20000); await cosmetics(); await sleep(2200);
    await scrollToSel(".flow-summary", 1400); await sleep(1600);
    // The admin's contact button needs CONTACT_URL, which the local stack does not set: draw it for the demo.
    await evaluate(`(() => { if (document.querySelector('#contact-admin')) return; const card = document.querySelector('.signup-quote');
      const a = document.createElement('a'); a.id = 'contact-admin'; a.className = 'btn-primary mt-3'; a.href = '#'; a.textContent = '✈ Adminga yozish'; a.onclick = (e) => e.preventDefault();
      card.appendChild(a); })()`);
    await scrollToSel("#contact-admin", 1200); await sleep(400);
    await click("#contact-admin"); await sleep(1800); stop();
  },
  async site_home() {
    await goto(SITE + "/"); start(); await sleep(2600);
    await scrollBy(700, 2000); await scrollBy(900, 2200); await scrollBy(900, 2200); await scrollBy(900, 2200); await scrollBy(1000, 2200); await sleep(400); stop();
  },
  async site_posts() {
    await goto(SITE + "/posts"); start(); await sleep(2200); await scrollBy(800, 2000); await scrollBy(800, 1800);
    await scrollTo(0, 1400); await click(".archive-grid .card-link, .archive-grid a"); await waitFor("document.querySelector('article, .post-body, main h1')", 15000); await sleep(2400);
    await scrollBy(700, 2000); await sleep(400); stop();
  },
  async site_tags() {
    await goto(SITE + "/tags"); start(); await sleep(3200); await scrollBy(400, 1600);
    await clickText("Shaxslar", "button, a"); await sleep(3200); stop();
  },
  async site_search() {
    await goto(SITE + "/search"); start(); await sleep(1500);
    await type(".search-field input, input[type='search'], main form input", "Toshkent", 110);
    await evaluate(`(() => { const i = document.querySelector(".search-field input, input[type='search'], main form input"); i.form?.requestSubmit(); return true; })()`);
    await waitFor("location.search.includes('Toshkent') && document.querySelectorAll('.card').length > 3", 20000); await sleep(3500);
    await scrollBy(600, 2200); await sleep(300); stop();
  },
  async site_chat() {
    await goto(SITE + "/chat"); start(); await sleep(1800);
    await type("form input.input-field", "Inflyatsiya haqida oxirgi paytda nima yozgan?", 55);
    await click("form button.btn-primary");
    await waitFor("document.querySelectorAll('a[href*=\"/post/\"]').length > 0", 90000);
    // Let the answer finish streaming: the ask button is enabled again once it has.
    await waitFor("!document.querySelector('form button.btn-primary').disabled && document.querySelector('form input.input-field').value === ''", 90000);
    await sleep(4000); await scrollBy(400, 2200); await sleep(800); stop();
  },
  async site_chat_idle() {
    // The assistant needs API credit to answer; until then the page is shown with a question typed.
    await goto(SITE + "/chat"); start(); await sleep(2200);
    await type("form input.input-field", "Inflyatsiya haqida oxirgi paytda nima yozgan?", 55); await sleep(2600); stop();
  },
  async site_graph() {
    await goto(SITE + "/graph"); start(); await sleep(4500); stop();
  },
  async site_stories() {
    await goto(SITE + "/stories"); start(); await sleep(2000); await click("main a[href*='/stories/']"); await sleep(3200); await scrollBy(600, 1800); stop();
  },
  async site_top() {
    await goto(SITE + "/top"); start(); await sleep(2400); await scrollBy(700, 2000); stop();
  },
};
try { await scenes[scene](); } catch (e) { console.error("scene failed:", e.message); process.exitCode = 1; }
await sleep(200); chrome.kill(); process.exit();
