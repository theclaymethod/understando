// Build the fixture run folder once. Each test copies it, so tests do not share my-work.
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

export default function globalSetup() {
  const here = fileURLToPath(new URL(".", import.meta.url));
  const bin = process.env.UNDERSTANDO_LEARN_BIN ?? join(here, "..", "..", "target", "release", "understando-learn");
  if (!existsSync(bin)) throw new Error(`Build the binary first: cargo build --release (missing ${bin})`);
  const work = mkdtempSync(join(tmpdir(), "learn-e2e-template-"));
  execFileSync("bash", [join(here, "make-fixture-run.sh"), work], { stdio: "inherit" });
  process.env.LEARN_E2E_TEMPLATE = work;
  process.env.UNDERSTANDO_LEARN_BIN = bin;
  return () => rmSync(work, { recursive: true, force: true });
}
