// issue-488 testing-plan T5 + T9: the explainer page template, headless.
//
//   npm i --prefix docs/specs/issue-488/evidence/ui playwright@1 axe-core@4
//   node docs/specs/issue-488/evidence/ui/check.mjs skills/the-loop/templates/explainer.html [outDir]
//
// Fills the template with a fixture quiz (one option carries a <script> string,
// abuse case 3), then checks: tabs + arrow keys, zero feedback before a
// selection, feedback after, no network request, no page error, no horizontal
// scroll at 375 px, the <script> text rendered as text, and an axe-core pass.
// Screenshots land in outDir (default: this directory). Exit code 1 on any failure.
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(here, 'package.json'));
const { chromium } = require('playwright');
const axeSource = readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');

const template = resolve(process.argv[2]);
const out = resolve(process.argv[3] || here);
const HOSTILE = '<script>window.__pwned = true</script><img src=x onerror="window.__pwned=true">';
const quiz = {
  questions: [
    { q: 'Q1: who decides when two people edit the box?', options: ['The first editor', 'The latest editor', HOSTILE, 'Nobody'], answer: 1, why: 'The newest edit is the one that counts.' },
    { q: 'Q2: what does an unticked row record?', options: ['Four declared skips', 'One skip', 'Nothing', 'A warning'], answer: 0, why: 'One row, four nodes.' },
    { q: 'Q3: why two nodes per quiz?', options: ['Labels', 'Skip sets', 'Artifacts', 'A session never works at a human node'], answer: 3, why: 'Human nodes are not worked by a session.' },
  ],
};
// The authoring rule the template states: a QUIZ block's JSON writes every "<"
// as \u003c, so no string can close the <script> element it sits in.
const block = (value) => JSON.stringify(value).replace(/</g, '\\u003c');
let html = readFileSync(template, 'utf8')
  .replace(/\{\{[^}]*\}\}/g, 'Fixture text')
  .replace(/(<script type="application\/json" id="quiz-spec">)[\s\S]*?(<\/script>)/, `$1${block(quiz)}$2`)
  .replace(/(<script type="application\/json" id="quiz-code">)[\s\S]*?(<\/script>)/, `$1${block({ questions: quiz.questions.slice(0, 1) })}$2`);
const page_ = join(mkdtempSync(join(tmpdir(), 'explainer-')), 'explainer.html');
writeFileSync(page_, html);
const url = 'file://' + page_;

const failures = [];
const check = (ok, what) => { console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`); if (!ok) failures.push(what); };
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || '/usr/bin/chromium' });
for (const scheme of ['light', 'dark']) {
  const page = await browser.newPage({ viewport: { width: 820, height: 1000 }, colorScheme: scheme });
  const errors = [], network = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('request', r => { if (!r.url().startsWith('file:')) network.push(r.url()); });
  await page.goto(url);
  await page.screenshot({ path: join(out, `spec-explainer-${scheme}.png`), fullPage: true });
  await page.click('#tab-specquiz');
  check(await page.locator('.feedback').count() === 0, `${scheme}: no feedback before a selection`);
  check(await page.locator('[aria-label*="correct" i], .correct, [data-answer]').count() === 0, `${scheme}: no answer leaked in markup`);
  await page.locator('input[name="quiz-spec-q0"]').nth(0).check();
  await page.locator('input[name="quiz-spec-q1"]').nth(0).check();
  check(await page.locator('.feedback').count() === 2, `${scheme}: feedback after selecting`);
  check((await page.locator('[data-progress="quiz-spec"]').textContent()).trim() === '2 of 3 answered', `${scheme}: progress line`);
  check(await page.getByText('<script>window.__pwned', { exact: false }).count() >= 1, `${scheme}: hostile option rendered as text`);
  await page.locator('input[name="quiz-spec-q0"]').nth(2).check();
  check(await page.evaluate(() => window.__pwned !== true), `${scheme}: hostile option never executed`);
  await page.screenshot({ path: join(out, `spec-quiz-${scheme}.png`), fullPage: true });
  await page.focus('#tab-specquiz'); await page.keyboard.press('ArrowRight');
  check((await page.locator('[role=tab][aria-selected=true]').textContent()) === 'Explainer', `${scheme}: ArrowRight moves to the next tab`);
  await page.keyboard.press('End');
  check((await page.locator('[role=tab][aria-selected=true]').textContent()) === 'Code quiz', `${scheme}: End moves to the last tab`);
  await page.locator('input[name="quiz-code-q0"]').nth(1).check();
  await page.screenshot({ path: join(out, `code-quiz-${scheme}.png`), fullPage: true });
  await page.addScriptTag({ content: axeSource });
  const axe = await page.evaluate(async () => (await window.axe.run(document)).violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.length })));
  console.log(`${scheme}: axe violations ${JSON.stringify(axe)}`);
  check(!axe.some(v => v.impact === 'serious' || v.impact === 'critical'), `${scheme}: no serious/critical axe violations`);
  check(errors.length === 0, `${scheme}: no page errors ${JSON.stringify(errors)}`);
  check(network.length === 0, `${scheme}: no network requests ${JSON.stringify(network)}`);
  await page.close();
}
const mobile = await browser.newPage({ viewport: { width: 375, height: 800 } });
await mobile.goto(url);
check(!(await mobile.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)), 'mobile: no horizontal scroll at 375 px');
await mobile.screenshot({ path: join(out, 'spec-explainer-mobile.png'), fullPage: true });
// The flow, frame by frame, for the GIF (assembled with ffmpeg by the caller).
const flow = await browser.newPage({ viewport: { width: 820, height: 760 } });
await flow.goto(url); await flow.click('#tab-specquiz');
const frames = [];
for (const [q, o] of [[null, null], [0, 0], [0, 1], [1, 0]]) {
  if (q !== null) await flow.locator(`input[name="quiz-spec-q${q}"]`).nth(o).check();
  const f = join(out, `flow-${frames.length}.png`); await flow.screenshot({ path: f }); frames.push(f);
}
console.log('flow frames', frames.length);
await browser.close();
if (failures.length) { console.log(`\n${failures.length} check(s) failed`); process.exit(1); }
console.log('\nall checks passed');
