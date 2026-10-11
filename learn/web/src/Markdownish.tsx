import { useEffect, useState } from "react";
import { MermaidBlock } from "@ve/components";

// Mermaid ships inside the app, so MermaidBlock does not fetch it from a CDN.
let mermaidReady: Promise<void> | null = null;
function loadMermaid() {
  mermaidReady ??= import("mermaid").then((m) => { (window as unknown as { mermaid: unknown }).mermaid = m.default; });
  return mermaidReady;
}

function Mermaid({ chart }: { chart: string }) {
  const [ready, setReady] = useState(false);
  useEffect(() => { loadMermaid().then(() => setReady(true)).catch(() => setReady(false)); }, []);
  if (!ready) return <pre className="learn-pre">{chart}</pre>;
  return <MermaidBlock chart={chart} caption="Model-generated diagram (guess tier)" />;
}

/** Plain text with fenced code blocks. Mermaid fences render as diagrams. No HTML from the model. */
export function Markdownish({ text }: { text: string }) {
  const parts = text.split(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)(?:```|$)/g);
  const out = [];
  for (let i = 0; i < parts.length; i += 3) {
    if (parts[i]) out.push(<p key={`t${i}`} className="learn-text">{parts[i]}</p>);
    if (i + 2 < parts.length) {
      const lang = parts[i + 1];
      const body = parts[i + 2];
      out.push(lang === "mermaid" ? <Mermaid key={`m${i}`} chart={body} /> : <pre key={`c${i}`} className="learn-pre"><code>{body}</code></pre>);
    }
  }
  return <>{out}</>;
}
