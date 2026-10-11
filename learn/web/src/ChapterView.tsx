import React, { useEffect, useMemo, useState, type ComponentType } from "react";
import * as runtime from "react/jsx-runtime";
import { run } from "@mdx-js/mdx";
import * as VE from "@ve/components";
import { getJson } from "./api";
import { askTutor } from "./tutor-bus";

export type Chapter = { id: string; title: string; heading?: string; aliases?: string[]; code: string };
export type Chapters = { schema: number; title: string; summary: string; head: string; source: string; css?: string; chapters: Chapter[] };

/** The chapter that holds an element id, for links such as #claim-c01. */
export function chapterOfAnchor(data: Chapters, anchor: string) {
  const needle = JSON.stringify(anchor);
  return data.chapters.find((c) => c.code.includes(`id: ${needle}`) || c.id === anchor);
}

type Props = Record<string, unknown> & { code?: string; filename?: string; language?: string };

/** The Artifacture CodeBlock, plus a button that sends the snippet to the tutor. */
function CodeBlockWithTutor(props: Props) {
  const Base = VE.CodeBlock;
  return (
    <div className="learn-code">
      <Base {...props} />
      <button
        type="button"
        className="learn-link"
        onClick={() => askTutor({
          message: `Explain this snippet at my level.${props.filename ? ` It is ${props.filename}.` : ""}`,
          context: { selection: String(props.code ?? "").slice(0, 6000), chapter: String(props.filename ?? "") },
        })}
      >
        Explain this snippet at my level
      </button>
    </div>
  );
}

const components = { ...(VE as unknown as Record<string, ComponentType<Props>>), CodeBlock: CodeBlockWithTutor };

class Boundary extends React.Component<{ children: React.ReactNode; resetKey: string }, { error: string }> {
  state = { error: "" };
  static getDerivedStateFromError(e: Error) { return { error: e.message }; }
  componentDidUpdate(prev: { resetKey: string }) { if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: "" }); }
  render() {
    return this.state.error
      ? <p role="alert" className="learn-error">This chapter did not render: {this.state.error}. Build the app against the Artifacture checkout that made the chapters (UNDERSTANDO_VE_RUNTIME).</p>
      : this.props.children;
  }
}

function Compiled({ chapter, anchor }: { chapter: Chapter; anchor?: string }) {
  const [Content, setContent] = useState<ComponentType<{ components: typeof components }> | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    setContent(null);
    setError("");
    run(chapter.code, { ...runtime, baseUrl: location.href })
      .then((mod) => { if (!cancelled) setContent(() => mod.default as ComponentType<{ components: typeof components }>); })
      .catch((e: Error) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [chapter]);
  useEffect(() => {
    if (!Content || !anchor) return;
    requestAnimationFrame(() => document.getElementById(anchor)?.scrollIntoView({ block: "start" }));
  }, [Content, anchor]);
  if (error) return <p role="alert" className="learn-error">This chapter did not render: {error}</p>;
  if (!Content) return <p role="status">Loading the chapter…</p>;
  return <Content components={components} />;
}

export function useChapters() {
  const [data, setData] = useState<Chapters | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { getJson<Chapters>("/api/chapters").then(setData).catch((e: Error) => setError(e.message)); }, []);
  return { data, error };
}

export function ChapterView({ data, id, anchor, children }: { data: Chapters; id: string; anchor?: string; children?: React.ReactNode }) {
  const chapter = useMemo(() => data.chapters.find((c) => c.id === id) ?? data.chapters[0], [data, id]);
  if (!chapter) return <p>This run has no chapters.</p>;
  return (
    <article className="learn-chapter" aria-labelledby="chapter-title" data-chapter={chapter.id}>
      <p className="learn-kicker">This chapter is pre-generated at fact tier, from the trust map and the recorded runs.</p>
      <h1 id="chapter-title" className="learn-sr">{chapter.title}</h1>
      {data.css && <style>{data.css}</style>}
      <Boundary resetKey={chapter.id}><Compiled chapter={chapter} anchor={anchor} /></Boundary>
      {children}
    </article>
  );
}
