// Artifacture's visual-explainer components, imported from its checkout through the @ve alias.
// The app type-checks its own code only; Artifacture checks its own files.
declare module "@ve/components" {
  import type { ComponentType } from "react";
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  type Any = ComponentType<any>;
  export const ExplainerShell: Any;
  export const Section: Any;
  export const Callout: Any;
  export const CodeBlock: Any;
  export const TerminalBlock: Any;
  export const DiagramCanvas: Any;
  export const MermaidBlock: Any;
  const all: Record<string, unknown>;
  export default all;
}
declare module "@ve/global.css";
