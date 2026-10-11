// A small bus: chapters and exercises send a question to the tutor panel.
export type TutorAsk = { message: string; context?: Record<string, string> };
const EVENT = "understando:ask-tutor";

export function askTutor(ask: TutorAsk) {
  window.dispatchEvent(new CustomEvent<TutorAsk>(EVENT, { detail: ask }));
}

export function onAskTutor(handler: (ask: TutorAsk) => void) {
  const listener = (e: Event) => handler((e as CustomEvent<TutorAsk>).detail);
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}
