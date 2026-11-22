"use client";

// Hien cau tra loi DA KIEM TRA XONG mot cach muot: dung markdown hoan chinh
// MOT lan, roi cho tung khoi (doan, dong danh sach) mo dan len lan luot.
// Thay cho kieu go chu tung tu truoc day - moi khung hinh dung lai markdown
// nen danh sach / chu dam bat ra giat cuc, chieu cao bong bong nhay lien tuc.
// Khong stream token tu model: backend con cac buoc kiem tra sau model
// (grounding, phan loai an toan) co the thay ca cau tra loi.

import { useEffect, useLayoutEffect, useState, type RefObject } from "react";

const BLOCK_SELECTOR = "p, li, h1, h2, h3, h4, blockquote, pre, table";
const MAX_TOTAL_MS = 1100;
const MAX_STEP_MS = 110;
const BLOCK_DURATION_MS = 380;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true
  );
}

// Gan do tre tang dan cho tung khoi trong `bodyRef`, va dat bien CSS
// --capy-reveal-after len `rootRef` = luc khoi cuoi hien xong (nut goi y,
// nguon tham khao dung bien nay de hien SAU phan chu).
export function useBlockReveal(
  rootRef: RefObject<HTMLElement | null>,
  bodyRef: RefObject<HTMLElement | null>,
  enabled: boolean,
): void {
  useLayoutEffect(() => {
    const root = rootRef.current;
    const body = bodyRef.current;
    if (!enabled || !root || !body || prefersReducedMotion()) return;
    const blocks = Array.from(body.querySelectorAll<HTMLElement>(BLOCK_SELECTOR)).filter(
      (el) => !el.parentElement?.closest("li, blockquote"),
    );
    const step = blocks.length > 1 ? Math.min(MAX_STEP_MS, MAX_TOTAL_MS / blocks.length) : 0;
    blocks.forEach((el, index) => {
      el.style.animationDelay = `${Math.round(index * step)}ms`;
      el.classList.add("capy-reveal-block");
    });
    const after = Math.round(Math.max(0, blocks.length - 1) * step + BLOCK_DURATION_MS * 0.6);
    root.style.setProperty("--capy-reveal-after", `${after}ms`);
  }, [rootRef, bodyRef, enabled]);
}

// Dong trang thai luc cho: doi dan theo thoi gian de nguoi dung biet Capy van
// dang lam (cau tra loi tra cuu thuoc / web mat 3-7 s).
const PENDING_HINTS: Array<[number, string]> = [
  [0, "Capy đang đọc câu hỏi của bạn…"],
  [2500, "Capy đang tra cứu thông tin…"],
  [6000, "Capy đang soạn câu trả lời cho bạn…"],
];

export function usePendingHint(pending: boolean): string {
  const [hint, setHint] = useState(PENDING_HINTS[0][1]);
  useEffect(() => {
    if (!pending) return;
    // Moc 0 ms dat lai dong dau cho moi lan cho moi; cleanup huy het khi xong.
    const timers = PENDING_HINTS.map(([delay, text]) =>
      window.setTimeout(() => setHint(text), delay),
    );
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [pending]);
  return hint;
}
