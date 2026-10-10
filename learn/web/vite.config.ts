import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { join, resolve } from "node:path";

import { veRuntime } from "./scripts/ve-runtime.mjs";

// The chapters use the Artifacture components, so the app looks like the static explainer.
function artifacture(): string {
  const dir = veRuntime();
  if (!dir) throw new Error("Artifacture is missing. Set UNDERSTANDO_VE_RUNTIME to a checkout that holds visual-explainer-mdx/components.tsx.");
  return dir;
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
