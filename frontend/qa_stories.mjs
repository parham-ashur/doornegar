/**
 * Doornegar QA — End-to-end content quality check
 *
 * Opens the production homepage on a mobile viewport, then clicks
 * through every story link and verifies each story detail page has
 * the expected content sections. Reports missing/broken content.
 *
 * Run from frontend/ directory:
 *   node qa_stories.mjs
 *   node qa_stories.mjs --url https://localhost:3000  # local dev
 *
 * Requires: npm install --no-save playwright && npx playwright install chromium
 */

import { chromium, devices } from "playwright";

const BASE =
  process.argv.find((a) => a.startsWith("--url="))?.split("=")[1] ||
  "https://frontend-tau-six-36.vercel.app";
const LOCALE = "fa";
const HOME = `${BASE}/${LOCALE}`;
const TIMEOUT = 30_000;

const results = { homepage: {}, stories: [], pass: 0, fail: 0, warn: 0 };

function pass(ctx, msg) {
  results.pass++;
  console.log(`  ✓ ${msg}`);
}
function fail(ctx, msg) {
  results.fail++;
  ctx.issues = ctx.issues || [];
  ctx.issues.push(msg);
  console.log(`  ✗ ${msg}`);
}
function warn(ctx, msg) {
  results.warn++;
  ctx.warnings = ctx.warnings || [];
  ctx.warnings.push(msg);
  console.log(`  ⚠ ${msg}`);
}

const browser = await chromium.launch();
const context = await browser.newContext({
  ...devices["iPhone 14"],
  locale: "fa-IR",
});

// ═══════════════════════════════════════════════════════════
// HOMEPAGE CHECKS
// ═══════════════════════════════════════════════════════════

console.log("\n══════ HOMEPAGE ══════");
console.log(`URL: ${HOME}`);

const homePage = await context.newPage();
await homePage.goto(HOME, { waitUntil: "networkidle", timeout: 60_000 });

const hCtx = results.homepage;

// Hero
const heroTitle = await homePage.locator("h1").first().innerText().catch(() => "");
if (heroTitle.length > 5) pass(hCtx, `Hero title: ${heroTitle.slice(0, 50)}...`);
else fail(hCtx, "Hero title missing or too short");

// Hero image
const heroImgs = await homePage.locator("main img, div img").first().evaluate((el) => ({
  src: el.currentSrc || el.src || "",
  broken: el.naturalWidth === 0,
})).catch(() => ({ src: "", broken: true }));
if (heroImgs.src && !heroImgs.broken) pass(hCtx, "Hero image loads");
else fail(hCtx, `Hero image broken or missing: ${heroImgs.src?.slice(0, 60)}`);

// Bias comparison on hero (check for the colored border divs)
const biasBlocks = await homePage.locator('[class*="border-r-2"]').count();
if (biasBlocks >= 2) pass(hCtx, `Hero bias comparison: ${biasBlocks} side panels`);
else if (biasBlocks === 1) warn(hCtx, "Hero bias comparison: only 1 side shown");
else warn(hCtx, "Hero bias comparison: not visible (may be below fold or no data)");

// Telegram strip on hero
const tgStrip = await homePage.locator("text=تحلیل روایت‌های تلگرام").count();
if (tgStrip > 0) pass(hCtx, "Telegram analysis section present");
else warn(hCtx, "Telegram analysis section not found on homepage");

// Blindspot section
const blindspotHeader = await homePage.locator("text=نگاه یک‌جانبه").count();
if (blindspotHeader > 0) pass(hCtx, "Blindspot section present");
else warn(hCtx, "Blindspot section missing");

// Most visited
const mostVisited = await homePage.locator("text=پرمخاطب‌ترین").count();
if (mostVisited > 0) pass(hCtx, "Most visited section present");
else warn(hCtx, "Most visited section missing");

// Weekly digest
const weeklyDigest = await homePage.locator("text=خلاصه هفتگی").count();
if (weeklyDigest > 0) pass(hCtx, "Weekly digest present");
else warn(hCtx, "Weekly digest missing");

// Words of week
const wordsOfWeek = await homePage.locator("text=واژه‌های روز").count();
if (wordsOfWeek > 0) pass(hCtx, "Words of week present");
else warn(hCtx, "Words of week missing");

// Placeholder icons (newspaper fallback = missing image)
const placeholders = await homePage.locator("svg.lucide-newspaper").count();
if (placeholders === 0) pass(hCtx, "No placeholder images on homepage");
else fail(hCtx, `${placeholders} placeholder image(s) on homepage`);

// Collect all story links
const storyLinks = await homePage.evaluate(() => {
  const links = new Set();
  document.querySelectorAll('a[href*="/stories/"]').forEach((a) => {
    const href = a.getAttribute("href");
    if (href && href.match(/\/stories\/[0-9a-f-]{36}/)) {
      links.add(href);
    }
  });
  return [...links];
});
console.log(`\nFound ${storyLinks.length} unique story links on homepage.\n`);

// ═══════════════════════════════════════════════════════════
// STORY DETAIL CHECKS
// ═══════════════════════════════════════════════════════════

for (const [i, link] of storyLinks.entries()) {
  const url = link.startsWith("http") ? link : `${BASE}${link}`;
  const storyId = link.match(/([0-9a-f-]{36})/)?.[1] || "?";
  const sCtx = { id: storyId, url, issues: [], warnings: [] };
  results.stories.push(sCtx);

  console.log(`══════ STORY ${i + 1}/${storyLinks.length} ══════`);
  console.log(`ID: ${storyId}`);

  const page = await context.newPage();
  try {
    await page.goto(url, { waitUntil: "networkidle", timeout: TIMEOUT });

    // Title
    const title = await page.locator("h1").first().innerText().catch(() => "");
    sCtx.title = title.slice(0, 80);
    if (title.length > 5) pass(sCtx, `Title: ${title.slice(0, 50)}...`);
    else fail(sCtx, "Title missing or too short");

    // Coverage bar
    const coverageBar = await page.locator('[class*="bg-[#1e3a5f]"]').count();
    if (coverageBar > 0) pass(sCtx, "Coverage bar visible");
    else warn(sCtx, "Coverage bar not found");

    // Bias analysis panel (tabs: مقایسه روایت‌ها, روایت محافظه‌کار, روایت اپوزیسیون)
    const biasTabs = await page.locator("text=مقایسه روایت‌ها").count();
    if (biasTabs > 0) pass(sCtx, "Bias comparison tab present");
    else warn(sCtx, "Bias comparison tab missing");

    const conservTab = await page.locator("text=روایت محافظه‌کار").count();
    const opposTab = await page.locator("text=روایت اپوزیسیون").count();
    if (conservTab > 0 && opposTab > 0) pass(sCtx, "Both narrative tabs present");
    else if (conservTab > 0) warn(sCtx, "Only conservative narrative tab");
    else if (opposTab > 0) warn(sCtx, "Only opposition narrative tab");
    else fail(sCtx, "No narrative tabs found");

    // Telegram section (button or expanded)
    const tgButton = await page.locator("text=دیدن تحلیل تلگرام").count();
    const tgExpanded = await page.locator("text=تحلیل روایت‌های تلگرام").count();
    if (tgButton > 0 || tgExpanded > 0) pass(sCtx, "Telegram section present");
    else warn(sCtx, "Telegram section missing");

    // Stats section
    const statsHeader = await page.locator("text=آمار").count();
    if (statsHeader > 0) pass(sCtx, "Stats section present");
    else warn(sCtx, "Stats section missing");

    // Articles list
    const articlesHeader = await page.locator("text=مقالات مرتبط").count();
    if (articlesHeader > 0) pass(sCtx, "Articles section present");
    else fail(sCtx, "Articles section missing");

    // Count actual article items (h3 elements after the articles heading)
    const articleCount = await page.locator("h3").count();
    if (articleCount >= 2) pass(sCtx, `${articleCount} article headings`);
    else warn(sCtx, `Only ${articleCount} article heading(s)`);

    // Placeholder images
    const storyPlaceholders = await page.locator("svg.lucide-newspaper").count();
    if (storyPlaceholders === 0) pass(sCtx, "No placeholder images");
    else warn(sCtx, `${storyPlaceholders} placeholder image(s)`);

  } catch (e) {
    fail(sCtx, `Page failed to load: ${e.message.slice(0, 80)}`);
  } finally {
    await page.close();
  }
  console.log("");
}

await browser.close();

// ═══════════════════════════════════════════════════════════
// SUMMARY
// ═══════════════════════════════════════════════════════════

console.log("\n══════════════════════════════════════════");
console.log("QA SUMMARY");
console.log("══════════════════════════════════════════");
console.log(`  ✓ Passed: ${results.pass}`);
console.log(`  ✗ Failed: ${results.fail}`);
console.log(`  ⚠ Warnings: ${results.warn}`);
console.log(`  Stories checked: ${results.stories.length}`);

if (results.fail > 0) {
  console.log("\n── FAILURES ──");
  if (results.homepage.issues?.length) {
    console.log("  Homepage:");
    for (const i of results.homepage.issues) console.log(`    ✗ ${i}`);
  }
  for (const s of results.stories) {
    if (s.issues?.length) {
      console.log(`  ${s.title || s.id}:`);
      for (const i of s.issues) console.log(`    ✗ ${i}`);
    }
  }
}

if (results.warn > 0) {
  console.log("\n── WARNINGS ──");
  if (results.homepage.warnings?.length) {
    console.log("  Homepage:");
    for (const w of results.homepage.warnings) console.log(`    ⚠ ${w}`);
  }
  for (const s of results.stories) {
    if (s.warnings?.length) {
      console.log(`  ${s.title || s.id}:`);
      for (const w of s.warnings) console.log(`    ⚠ ${w}`);
    }
  }
}

console.log("\nDone.");
process.exit(results.fail > 0 ? 1 : 0);
