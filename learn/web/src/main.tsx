import "@ve/global.css";
import "./app.css";
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { getJson, type Session } from "./api";
import { ChapterView, useChapters } from "./ChapterView";
import { EXERCISE_KINDS, ExercisesView, KIND_LABEL } from "./Exercises";
import { SetupView } from "./SetupView";
import { TutorPanel } from "./TutorPanel";

function useRoute() {
  const [hash, setHash] = useState(location.hash.slice(1));
  useEffect(() => {
    const f = () => setHash(location.hash.slice(1));
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return hash;
}

function App() {
  const route = useRoute();
  const { data, error } = useChapters();
  const [session, setSession] = useState<Session | null>(null);
  useEffect(() => { getJson<Session>("/api/session").then(setSession).catch(() => undefined); }, []);
  const [section, id] = route.split("/");
  const chapterId = section === "chapter" ? id : data?.chapters[0]?.id ?? "";
  const s = session?.summary ?? {};
  return (
    <div data-ve-preset="iso" className="learn-app">
      <header className="learn-header">
        <div>
          <p className="learn-kicker">understando learn</p>
          <h1>{data?.title || session?.title || "Trust map"}</h1>
          {session && <p className="learn-muted">{session.repo} #{session.pr ?? "?"} at {session.head.slice(0, 10)}. {["Proven", "Backed", "Asserted", "Gap"].map((k) => `${s[k] ?? 0} ${k}`).join(", ")}.</p>}
        </div>
      </header>
      <div className="learn-body">
        <nav className="learn-nav" aria-label="Chapters and exercises">
          <h2>Chapters</h2>
          <ul>{(data?.chapters ?? []).map((c) => (
            <li key={c.id}><a href={`#chapter/${c.id}`} aria-current={section !== "exercises" && section !== "setup" && chapterId === c.id ? "page" : undefined}>{c.title}</a></li>
          ))}</ul>
          <h2>Exercises</h2>
          <ul>{EXERCISE_KINDS.map((k) => <li key={k}><a href={`#exercises/${k}`} aria-current={section === "exercises" && id === k ? "page" : undefined}>{KIND_LABEL[k]}</a></li>)}</ul>
          <h2>App</h2>
          <ul><li><a href="#setup" aria-current={section === "setup" ? "page" : undefined}>Setup doctor</a></li>
            {session?.hasExplainerHtml && <li><a href="/run/explainer.html" target="_blank" rel="noreferrer">Static explainer</a></li>}</ul>
        </nav>
        <main className="learn-main">
          {section === "exercises" && <ExercisesView kind={id || "predict"} />}
          {section === "setup" && <SetupView />}
          {section !== "exercises" && section !== "setup" && (
            error ? <p role="alert" className="learn-error">{error}</p> : data ? <ChapterView data={data} id={chapterId} /> : <p role="status">Loading the chapters.</p>
          )}
        </main>
        <TutorPanel />
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
