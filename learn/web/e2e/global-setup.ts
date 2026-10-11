// Build the fixture run folder once. Each test copies it, so tests do not share my-work.
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir, userInfo } from "node:os";
import { join, sep } from "node:path";
import { fileURLToPath } from "node:url";

// The self-check of tests/isolate.sh: the test root is set, and it is not the real ~/.understando.
function selfCheck() {
  const root = process.env.UNDERSTANDO_TEST_ROOT;
  if (process.env.UNDERSTANDO_TEST !== "1" || !root) throw new Error("isolation: UNDERSTANDO_TEST and UNDERSTANDO_TEST_ROOT must be set (playwright.config.ts)");
  const real = join(userInfo().homedir, ".understando");
  const r = realpathSync(root);
  if (r === real || r.startsWith(real + sep) || real.startsWith(r + sep)) throw new Error(`isolation: the test root ${r} is the real ${real}, holds it or is in it`);
  if (!realpathSync(tmpdir()).startsWith(r + sep)) throw new Error(`isolation: TMPDIR ${tmpdir()} is not in the test root ${r}`);
}

export default function globalSetup() {
  selfCheck();
  const here = fileURLToPath(new URL(".", import.meta.url));
  const bin = process.env.UNDERSTANDO_LEARN_BIN ?? join(here, "..", "..", "target", "release", "understando-learn");
  if (!existsSync(bin)) throw new Error(`Build the binary first: cargo build --release (missing ${bin})`);
  const work = mkdtempSync(join(tmpdir(), "learn-e2e-template-"));
  execFileSync("bash", [join(here, "make-fixture-run.sh"), work], { stdio: "inherit" });
  process.env.LEARN_E2E_TEMPLATE = work;
  process.env.UNDERSTANDO_LEARN_BIN = bin;
  return () => rmSync(work, { recursive: true, force: true });
}
