"use client";

// Hook boc may trang thai thuan (capy-machine.ts) + cac bo hen gio (TASK-CAPY-21).
// Moi bo hen gio deu duoc huy khi doi trang thai / unmount - khong tich luy.

import { useCallback, useEffect, useReducer, useRef } from "react";
import { capyReducer, type CapyEvent, type CapyState } from "./capy-machine";

const TAP_COOLDOWN_MS = 4000;
const PROGRESS_TICK_MS = 1200;

export function useCapyBehavior(initial: CapyState = "IDLE") {
  const [state, dispatch] = useReducer(capyReducer, initial);
  const lastTap = useRef(0);

  // PROGRESS_TICK tu ve IDLE sau mot nhip.
  useEffect(() => {
    if (state !== "PROGRESS_TICK") return;
    const t = setTimeout(() => dispatch({ type: "DISMISS" }), PROGRESS_TICK_MS);
    return () => clearTimeout(t);
  }, [state]);

  const send = useCallback((ev: CapyEvent) => dispatch(ev), []);
  const tap = useCallback(() => {
    const now = Date.now();
    if (now - lastTap.current < TAP_COOLDOWN_MS) return;
    lastTap.current = now;
    dispatch({ type: "TAP" });
  }, []);
  const clipDone = useCallback(() => dispatch({ type: "CLIP_DONE" }), []);
  return { state, send, tap, clipDone };
}

/** Chao lan dau moi ngay (localStorage, mat cung khong sao). */
export function daChaoHomNay(): boolean {
  try {
    const key = `capy-greet:${new Date().toDateString()}`;
    if (localStorage.getItem(key)) return true;
    localStorage.setItem(key, "1");
  } catch {
    // bo qua
  }
  return false;
}
