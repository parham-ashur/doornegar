#!/usr/bin/env node
/**
 * i18n parity check — fails CI if any key in fa.json (the source of
 * truth) is missing from en.json or fr.json, or if EN/FR add stray
 * keys that don't exist in FA. Run via `npm run i18n:check`.
 *
 * Why: a translated copy that loses a key during refactor renders the
 * raw key path on the page (e.g. "story.no_stories") instead of a
 * translated string. CI catches drift before the regression ships.
 */

import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const messagesDir = resolve(__dirname, "..", "src", "messages");

const SOURCE = "fa";
const TARGETS = ["en", "fr"];

function flatten(obj, prefix = "") {
  const out = new Map();
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      for (const [subKey, subVal] of flatten(v, path)) {
        out.set(subKey, subVal);
      }
    } else {
      out.set(path, v);
    }
  }
  return out;
}

async function loadLocale(locale) {
  const path = resolve(messagesDir, `${locale}.json`);
  const raw = await readFile(path, "utf8");
  return JSON.parse(raw);
}

const sourceFlat = flatten(await loadLocale(SOURCE));
const sourceKeys = new Set(sourceFlat.keys());

let problems = 0;
for (const locale of TARGETS) {
  const targetFlat = flatten(await loadLocale(locale));
  const targetKeys = new Set(targetFlat.keys());

  const missing = [...sourceKeys].filter((k) => !targetKeys.has(k));
  const stray = [...targetKeys].filter((k) => !sourceKeys.has(k));

  if (missing.length === 0 && stray.length === 0) {
    console.log(`✓ ${locale}: parity with ${SOURCE} (${sourceKeys.size} keys)`);
    continue;
  }

  if (missing.length > 0) {
    console.error(`✗ ${locale}.json missing ${missing.length} key(s) from ${SOURCE}.json:`);
    for (const k of missing) console.error(`    - ${k}`);
    problems += missing.length;
  }
  if (stray.length > 0) {
    console.error(`✗ ${locale}.json has ${stray.length} stray key(s) not in ${SOURCE}.json:`);
    for (const k of stray) console.error(`    + ${k}`);
    problems += stray.length;
  }
}

// ICU placeholder parity — `{count}` etc. must appear in both source
// and target so an interpolation doesn't silently drop on translation.
const placeholderPattern = /\{[a-zA-Z_][a-zA-Z0-9_]*\}/g;
for (const locale of TARGETS) {
  const targetFlat = flatten(await loadLocale(locale));
  for (const [key, srcVal] of sourceFlat) {
    if (typeof srcVal !== "string") continue;
    const targetVal = targetFlat.get(key);
    if (typeof targetVal !== "string") continue;
    const srcPlaceholders = new Set(srcVal.match(placeholderPattern) ?? []);
    const tgtPlaceholders = new Set(targetVal.match(placeholderPattern) ?? []);
    for (const p of srcPlaceholders) {
      if (!tgtPlaceholders.has(p)) {
        console.error(
          `✗ ${locale}.json:${key} missing ICU placeholder ${p} (source has it)`,
        );
        problems += 1;
      }
    }
    for (const p of tgtPlaceholders) {
      if (!srcPlaceholders.has(p)) {
        console.error(
          `✗ ${locale}.json:${key} has stray ICU placeholder ${p} (not in source)`,
        );
        problems += 1;
      }
    }
  }
}

if (problems > 0) {
  console.error(`\n${problems} i18n parity problem(s). Failing.`);
  process.exit(1);
}
console.log(`\nAll ${TARGETS.length} locale(s) in parity with ${SOURCE}.json.`);
