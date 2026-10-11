#!/usr/bin/env node
// Compile the per-PR chapter MDX of one run folder ahead of time, at explain time.
//
//   node learn/web/scripts/compile-chapters.mjs <run-dir>
//
// Input: <run-dir>/explainer.mdx. When it imports one MDX unit per chapter from chapters/, each
// <Section> of the entry is one chapter. Else the file is split at each top-level <Section>.
// Output: <run-dir>/learn/chapters.json. Each chapter holds MDX compiled to a function body.
// The app runs it with the Artifacture components that it embeds, so the learner needs no Node.
import { compile } from "@mdx-js/mdx";
import { existsSync } from "node:fs";
import { mkdir, readFile, readdir, rename, writeFile } from "node:fs/promises";
import { basename, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { veRuntime } from "./ve-runtime.mjs";

const runDir = process.argv[2] && resolve(process.argv[2]);
if (!runDir) {
  console.error("usage: compile-chapters.mjs <run-dir>");
  process.exit(2);
}

// Artifacture's preflight checks the diagrams and adds the highlighted HTML to each CodeBlock,
// as its HTML export does. Without it the chapters still compile, with plain code blocks.
async function preflight(code, id) {
  const ve = veRuntime();
  if (!ve) return code;
  const { preflightSource } = await import(pathToFileURL(join(ve, "scripts", "ve-mdx", "integrity.mjs")).href);
  return (await preflightSource(code, { id, draft: true })).code;
}

const IMPORT = /^import\s.+?from\s+['"][^'"]+['"];?\s*$/gm;
const SECTION_OPEN = /^<Section\b([^>]*)>\s*$/;

function slug(text, index) {
  const s = text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 48);
  return `${String(index + 1).padStart(2, "0")}-${s || "chapter"}`;
}

function shellProps(source) {
  const open = /<ExplainerShell\b([^>]*)>/.exec(source);
  const prop = (name) => {
    const m = new RegExp(`${name}=(?:"([^"]*)"|\\{"((?:[^"\\\\]|\\\\.)*)"\\})`).exec(open?.[1] ?? "");
    return m ? (m[1] ?? JSON.parse(`"${m[2]}"`)) : "";
  };
  return { title: prop("title"), summary: prop("summary") };
}

/** Split an explainer at each top-level Section. Lines outside a Section go to an intro chapter. */
function splitSections(source) {
  const lines = source.replace(IMPORT, "").split("\n");
  const chapters = [];
  let current = null;
  const intro = [];
  for (const line of lines) {
    if (/^<\/?ExplainerShell\b/.test(line) || /^\{\/\*.*\*\/\}\s*$/.test(line)) continue;
    const open = SECTION_OPEN.exec(line);
    if (open && !current) {
      current = { id: attr(line, "id"), title: attr(line, "navLabel") || attr(line, "title"), heading: attr(line, "title"), lines: [line] };
      continue;
    }
    if (current) {
      current.lines.push(line);
      if (/^<\/Section>\s*$/.test(line)) {
        chapters.push({ id: current.id, title: current.title, heading: current.heading, mdx: current.lines.join("\n") });
        current = null;
      }
    } else if (line.trim()) intro.push(line);
  }
  if (current) throw new Error(`The Section "${current.title}" has no closing tag at the start of a line.`);
  if (intro.length) chapters.unshift({ title: "Overview", mdx: intro.join("\n") });
  return chapters;
}

const CHAPTER_IMPORT = /^import\s+([A-Z][A-Za-z0-9]*)\s+from\s+['"](\.\/chapters\/[^'"]+\.mdx)['"];?\s*$/gm;
const SECTION_LINE = /^<Section\b[^>]*>\s*$/;

function attr(tag, name) {
  const m = new RegExp(`\\b${name}=(?:"([^"]*)"|\\{"((?:[^"\\\\]|\\\\.)*)"\\})`).exec(tag);
  return m ? (m[1] ?? JSON.parse(`"${m[2]}"`)) : "";
}

/** The explainer entry imports one MDX file per chapter and wraps each in a Section. */
async function entryChapters(text) {
  const imports = new Map([...text.matchAll(CHAPTER_IMPORT)].map((m) => [m[1], m[2]]));
  if (!imports.size) return null;
  const css = /<style>\{`([\s\S]*?)`\}<\/style>/.exec(text)?.[1] ?? "";
  const lines = text.split("\n");
  const chapters = [];
  for (let i = 0; i < lines.length; i++) {
    if (!SECTION_LINE.test(lines[i])) continue;
    const open = lines[i];
    const body = [];
    for (i++; i < lines.length && !/^<\/Section>\s*$/.test(lines[i]); i++) body.push(lines[i]);
    const parts = [];
    for (const line of body) {
      const m = /^<([A-Z][A-Za-z0-9]*)\s*\/>\s*$/.exec(line.trim());
      if (m && imports.has(m[1])) parts.push((await readFile(join(runDir, imports.get(m[1])), "utf8")).replace(IMPORT, "").replace(/^\{\/\*.*\*\/\}\s*$/gm, ""));
      else parts.push(line);
    }
    chapters.push({ id: attr(open, "id"), title: attr(open, "navLabel") || attr(open, "title"), heading: attr(open, "title"),
      mdx: [open, ...parts, "</Section>"].join("\n") });
  }
  return { css, chapters };
}

// The data that an explainer imports (import trust from './trust-map.json'). The app has no module
// loader for it, so each chapter that uses a name gets the data inline. A resolved-refs file gets
// its code highlighted, as the HTML export does.
const DATA_IMPORT = /^import\s+([A-Za-z_$][\w$]*)\s+from\s+['"](\.\/[^'"]+\.json)['"];?\s*$/gm;
async function dataImports(text) {
  const out = new Map();
  for (const [, name, file] of text.matchAll(DATA_IMPORT)) {
    let value = JSON.parse(await readFile(join(runDir, file), "utf8"));
    const ve = veRuntime();
    if (ve && value?.schema === 1 && Array.isArray(value.refs) && value.diff) {
      const { highlightRefs } = await import(pathToFileURL(join(ve, "scripts", "ve-mdx", "integrity.mjs")).href);
      value = await highlightRefs(value);
    }
    out.set(name, value);
  }
  return out;
}

/** The section anchors that a helper call computes from the data, for example anchors={promiseAnchors(trust, refs)}. */
async function inlineHelpers(mdx, data) {
  const ve = veRuntime();
  if (!ve || !/promiseAnchors\(/.test(mdx)) return mdx;
  const { promiseAnchors } = await import(pathToFileURL(join(ve, "visual-explainer-mdx", "trust-map-rules.ts")).href);
  return mdx.replace(/promiseAnchors\(\s*([A-Za-z_$][\w$]*)\s*,\s*([A-Za-z_$][\w$]*)\s*\)/g, (_m, map, refs) => JSON.stringify(promiseAnchors(data.get(map), data.get(refs))));
}

async function loadChapters() {
  const text = await readFile(join(runDir, "explainer.mdx"), "utf8");
  const entry = await entryChapters(text);
  if (entry) return { source: "explainer.mdx + chapters/", shell: shellProps(text), css: entry.css, chapters: entry.chapters };
  return { source: "explainer.mdx", shell: shellProps(text), css: "", chapters: splitSections(text) };
}

const { source, shell, css, chapters } = await loadChapters();
const data = await dataImports(await readFile(join(runDir, "explainer.mdx"), "utf8"));
if (!chapters.length) throw new Error("No chapters found.");
const compiled = [];
for (const [index, chapter] of chapters.entries()) {
  const id = chapter.id || slug(chapter.title, index);
  // The preflight checks that each component is imported, so give it the import line, then drop it.
  const names = [...new Set([...chapter.mdx.matchAll(/<([A-Z][A-Za-z0-9]*)/g)].map((m) => m[1]))];
  const header = names.length ? `import { ${names.join(", ")} } from 'visual-explainer-mdx/components';\n\n` : "";
  const body = await inlineHelpers(chapter.mdx, data);
  const inline = [...data].filter(([name]) => new RegExp(`\\b${name}\\b`).test(body)).map(([name, value]) => `export const ${name} = ${JSON.stringify(value)};\n\n`).join("");
  const prepared = inline + (await preflight(header + body, `${basename(runDir)}/${id}`)).replace(IMPORT, "");
  const code = String(await compile(prepared, { outputFormat: "function-body", development: false }));
  compiled.push({ id, title: chapter.title, heading: chapter.heading || chapter.title, code });
}
const trustMap = JSON.parse(await readFile(join(runDir, "trust-map.json"), "utf8"));
const out = {
  schema: 1,
  title: shell.title || trustMap.title || "",
  summary: shell.summary || "",
  head: trustMap.head,
  source,
  css,
  compiledAt: new Date().toISOString(),
  chapters: compiled,
};
await mkdir(join(runDir, "learn"), { recursive: true });
const target = join(runDir, "learn", "chapters.json");
await writeFile(`${target}.tmp`, JSON.stringify(out) + "\n");
await rename(`${target}.tmp`, target);
console.log(`compiled ${compiled.length} chapters from ${source} into ${target}`);
