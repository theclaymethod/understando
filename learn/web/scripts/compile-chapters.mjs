#!/usr/bin/env node
// Compile the per-PR chapter MDX of one run folder ahead of time, at explain time.
//
//   node learn/web/scripts/compile-chapters.mjs <run-dir>
//
// Input: <run-dir>/chapters/*.mdx when that folder exists (one file per chapter, in name
// order), else <run-dir>/explainer.mdx split at each top-level <Section title=...>.
// Output: <run-dir>/learn/chapters.json. Each chapter holds MDX compiled to a function body.
// The app runs it with the Artifacture components that it embeds, so the learner needs no Node.
import { compile } from "@mdx-js/mdx";
import { existsSync } from "node:fs";
import { mkdir, readFile, readdir, rename, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { basename, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const runDir = process.argv[2] && resolve(process.argv[2]);
if (!runDir) {
  console.error("usage: compile-chapters.mjs <run-dir>");
  process.exit(2);
}

function artifacture() {
  const candidates = [process.env.UNDERSTANDO_VE_RUNTIME, "/Users/clayton/dev/artifacture", join(homedir(), ".artifacture", "runtime")];
  for (const dir of candidates) if (dir && existsSync(join(dir, "scripts", "ve-mdx", "integrity.mjs"))) return resolve(dir);
  return null;
}

// Artifacture's preflight checks the diagrams and adds the highlighted HTML to each CodeBlock,
// as its HTML export does. Without it the chapters still compile, with plain code blocks.
async function preflight(code, id) {
  const ve = artifacture();
  if (!ve) return code;
  const { preflightSource } = await import(pathToFileURL(join(ve, "scripts", "ve-mdx", "integrity.mjs")).href);
  return (await preflightSource(code, { id, draft: true })).code;
}

const IMPORT = /^import\s.+?from\s+['"][^'"]+['"];?\s*$/gm;
const SECTION_OPEN = /^<Section\s+title=(?:"([^"]*)"|\{"((?:[^"\\]|\\.)*)"\})\s*>\s*$/;

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
      const title = open[1] ?? JSON.parse(`"${open[2]}"`);
      current = { title, lines: [line] };
      continue;
    }
    if (current) {
      current.lines.push(line);
      if (/^<\/Section>\s*$/.test(line)) {
        chapters.push({ title: current.title, mdx: current.lines.join("\n") });
        current = null;
      }
    } else if (line.trim()) intro.push(line);
  }
  if (current) throw new Error(`The Section "${current.title}" has no closing tag at the start of a line.`);
  if (intro.length) chapters.unshift({ title: "Overview", mdx: intro.join("\n") });
  return chapters;
}

async function loadChapters() {
  const dir = join(runDir, "chapters");
  if (existsSync(dir)) {
    const files = (await readdir(dir)).filter((f) => f.endsWith(".mdx")).sort();
    const out = [];
    for (const f of files) {
      const text = (await readFile(join(dir, f), "utf8")).replace(IMPORT, "");
      const title = SECTION_OPEN.exec(text.split("\n").find((l) => SECTION_OPEN.test(l)) ?? "")?.slice(1).find(Boolean) ?? basename(f, ".mdx");
      out.push({ title, mdx: text.replace(/^<\/?ExplainerShell\b.*$/gm, "") });
    }
    return { source: "chapters/", shell: {}, chapters: out };
  }
  const file = join(runDir, "explainer.mdx");
  const text = await readFile(file, "utf8");
  return { source: "explainer.mdx", shell: shellProps(text), chapters: splitSections(text) };
}

const { source, shell, chapters } = await loadChapters();
if (!chapters.length) throw new Error("No chapters found.");
const compiled = [];
for (const [index, chapter] of chapters.entries()) {
  const id = slug(chapter.title, index);
  // The preflight checks that each component is imported, so give it the import line, then drop it.
  const names = [...new Set([...chapter.mdx.matchAll(/<([A-Z][A-Za-z0-9]*)/g)].map((m) => m[1]))];
  const header = names.length ? `import { ${names.join(", ")} } from 'visual-explainer-mdx/components';\n\n` : "";
  const prepared = (await preflight(header + chapter.mdx, `${basename(runDir)}/${id}`)).replace(IMPORT, "");
  const code = String(await compile(prepared, { outputFormat: "function-body", development: false }));
  compiled.push({ id, title: chapter.title, code });
}
const trustMap = JSON.parse(await readFile(join(runDir, "trust-map.json"), "utf8"));
const out = {
  schema: 1,
  title: shell.title || trustMap.title || "",
  summary: shell.summary || "",
  head: trustMap.head,
  source,
  compiledAt: new Date().toISOString(),
  chapters: compiled,
};
await mkdir(join(runDir, "learn"), { recursive: true });
const target = join(runDir, "learn", "chapters.json");
await writeFile(`${target}.tmp`, JSON.stringify(out) + "\n");
await rename(`${target}.tmp`, target);
console.log(`compiled ${compiled.length} chapters from ${source} into ${target}`);
