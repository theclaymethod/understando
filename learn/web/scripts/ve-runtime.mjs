// The Artifacture checkout that holds visual-explainer-mdx/components.tsx.
// Order: $UNDERSTANDO_VE_RUNTIME, then the repo behind the visual-explainer skill link, then
// ~/.artifacture/runtime. The same rule as scripts/explain.py and tests/e2e.sh.
import { existsSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";

export function veRuntime() {
  const candidates = [process.env.UNDERSTANDO_VE_RUNTIME];
  try {
    const skill = realpathSync(join(homedir(), ".claude", "skills", "visual-explainer", "SKILL.md"));
    candidates.push(resolve(dirname(skill), "..", ".."));
  } catch { /* no skill link */ }
  candidates.push(join(homedir(), ".artifacture", "runtime"));
  for (const dir of candidates) if (dir && existsSync(join(dir, "visual-explainer-mdx", "components.tsx"))) return resolve(dir);
  return null;
}
