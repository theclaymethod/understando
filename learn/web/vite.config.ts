import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";

// The Artifacture checkout that holds visual-explainer-mdx/components.tsx. The chapters use
// these components, so the app looks like the static explainer.
function artifacture(): string {
  const candidates = [process.env.UNDERSTANDO_VE_RUNTIME, "/Users/clayton/dev/artifacture", join(homedir(), ".artifacture", "runtime")];
  for (const dir of candidates) if (dir && existsSync(join(dir, "visual-explainer-mdx", "components.tsx"))) return resolve(dir);
  throw new Error("Artifacture is missing. Set UNDERSTANDO_VE_RUNTIME to a checkout that holds visual-explainer-mdx/components.tsx.");
}
const ve = artifacture();

export default defineConfig({
  base: "/",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@ve": join(ve, "visual-explainer-mdx") },
    // components.tsx resolves react from the Artifacture install; keep one copy.
    dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime"],
  },
  server: { fs: { allow: [ve, resolve(".")] } },
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 6000 },
});
