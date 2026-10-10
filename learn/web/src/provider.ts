import { useSyncExternalStore } from "react";
import type { Provider } from "./api";

const KEY = "understando:tutor-provider";
const EVENT = "understando:provider-changed";

export function getProvider(): Provider | "" {
  try {
    const v = localStorage.getItem(KEY);
    return v === "claude" || v === "codex" ? v : "";
  } catch { return ""; }
}

export function setProvider(p: Provider) {
  try { localStorage.setItem(KEY, p); } catch { /* the choice lasts for this page only */ }
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(notify: () => void) {
  window.addEventListener(EVENT, notify);
  window.addEventListener("storage", notify);
  return () => { window.removeEventListener(EVENT, notify); window.removeEventListener("storage", notify); };
}

export function useProvider() {
  return useSyncExternalStore(subscribe, getProvider, () => "" as const);
}
