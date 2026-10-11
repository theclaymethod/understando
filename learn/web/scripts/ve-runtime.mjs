// The Artifacture checkout that holds visual-explainer-mdx/components.tsx.
// Order: $UNDERSTANDO_VE_RUNTIME, then ve_runtime in ~/.understando/config.toml, then the repo behind
// the visual-explainer skill link, then ~/.artifacture/runtime. The same rule as scripts/config.py.
import { existsSync, readFileSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";

export function veRuntime() {
  const candidates = [process.env.UNDERSTANDO_VE_RUNTIME];
  try {
    const home = process.env.UNDERSTANDO_HOME || join(homedir(), ".understando");
    const m = readFileSync(join(home, "config.toml"), "utf8").match(/^ve_runtime\s*=\s*"([^"]+)"/m);
    if (m) candidates.push(m[1]);
  } catch { /* no config */ }
  try {
    const skill = realpathSync(join(homedir(), ".claude", "skills", "visual-explainer", "SKILL.md"));
    candidates.push(resolve(dirname(skill), "..", ".."));
  } catch { /* no skill link */ }
  candidates.push(join(homedir(), ".artifacture", "runtime"));
  for (const dir of candidates) if (dir && existsSync(join(dir, "visual-explainer-mdx", "components.tsx"))) return resolve(dir);
  return null;
}
