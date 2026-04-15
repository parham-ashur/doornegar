import { chromium, devices } from 'playwright';

const HOME = 'https://frontend-tau-six-36.vercel.app/fa';
const STORY = 'https://frontend-tau-six-36.vercel.app/fa/stories/9b1b87ca-114e-4756-b922-52fe9c92d982';
const HOME_OUT = '/tmp/homepage_mobile.png';
const STORY_OUT = '/tmp/story_mobile.png';

const browser = await chromium.launch();

for (const [label, url, out] of [
  ['HOME', HOME, HOME_OUT],
  ['STORY', STORY, STORY_OUT],
]) {
  const ctx = await browser.newContext({
    ...devices['iPhone 14'],
    locale: 'fa-IR',
  });
  const page = await ctx.newPage();

  const broken = [];
  page.on('response', async (res) => {
    const u = res.url();
    const ct = res.headers()['content-type'] || '';
    if ((ct.startsWith('image/') || u.match(/\.(jpg|jpeg|png|webp|gif)/i)) && res.status() >= 400) {
      broken.push({ url: u, status: res.status() });
    }
  });

  console.log(`\n========== ${label} ==========`);
  console.log(`URL: ${url}`);
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  } catch (e) {
    console.log(`  nav error: ${e.message}`);
  }

  await page.evaluate(async () => {
    await new Promise((resolve) => {
      let total = 0;
      const step = () => {
        window.scrollBy(0, 400);
        total += 400;
        if (total < document.body.scrollHeight + 500) setTimeout(step, 150);
        else resolve();
      };
      step();
    });
  });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: out, fullPage: true });
  console.log(`  screenshot: ${out}`);

  const h1 = await page.locator('h1').first().innerText().catch(() => '(no h1)');
  console.log(`  h1: ${h1}`);

  const imgs = await page.locator('img').evaluateAll((nodes) =>
    nodes.map((n) => ({
      src: (n.currentSrc || n.src || '').slice(0, 110),
      w: n.naturalWidth,
      h: n.naturalHeight,
      displayW: n.offsetWidth,
      displayH: n.offsetHeight,
      broken: n.naturalWidth === 0,
    }))
  );
  console.log(`  ${imgs.length} images:`);
  for (const [i, img] of imgs.entries()) {
    const tag = img.broken
      ? 'BROKEN   '
      : `${String(img.w).padStart(4)}x${String(img.h).padStart(4)}`;
    console.log(`    [${String(i + 1).padStart(2)}] ${tag}  ${img.src}`);
  }

  if (broken.length) {
    console.log(`  network-broken: ${broken.length}`);
    for (const b of broken) console.log(`    ${b.status}  ${b.url.slice(0, 100)}`);
  }

  if (label === 'STORY') {
    const sections = await page.evaluate(() => {
      const out = [];
      const add = (el, label) => {
        if (!el) return;
        const rect = el.getBoundingClientRect();
        out.push({
          label,
          text: (el.textContent || '').slice(0, 60).trim(),
          top: Math.round(rect.top + window.scrollY),
        });
      };
      document.querySelectorAll('h1').forEach((e) => add(e, 'H1'));
      document.querySelectorAll('h2').forEach((e) => add(e, 'H2'));
      document.querySelectorAll('h3').forEach((e) => add(e, 'H3'));
      document.querySelectorAll('h4').forEach((e) => add(e, 'H4'));
      const mobileBlock = document.getElementById('telegram-mobile');
      add(mobileBlock, 'telegram-mobile container');
      return out.sort((a, b) => a.top - b.top);
    });
    console.log('\n  vertical section order (mobile):');
    for (const s of sections) {
      console.log(`    ${String(s.top).padStart(5)}px  [${s.label}] ${s.text}`);
    }
  }

  await ctx.close();
}

await browser.close();
console.log('\nDone.');
