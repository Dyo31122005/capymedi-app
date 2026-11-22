// May trang thai hanh vi cua Capy (TASK-CAPY-21, planning §5.8). HAM THUAN.
//
// Quyen so huu animation: clip glTF (AnimationMixer) so huu bone cua nhan vat;
// GSAP chi so huu group bao ngoai (nhay nhe khi tien do tang, chuyen giai doan)
// va mon an. Hai he thong khong bao gio ghi cung mot transform.

export type CapyState =
  | "IDLE"
  | "GREET"
  | "TAP_REACT"
  | "CURIOUS_WAIT"
  | "READY_TO_FEED"
  | "EATING"
  | "HAPPY"
  | "PROGRESS_TICK"
  | "GROWTH_CELEBRATION"
  | "SUPPORTIVE";

export type CapyEvent =
  | { type: "GREET_TODAY" }
  | { type: "TAP" }
  | { type: "PHOTO_PENDING" }
  | { type: "RESULT"; kind: "FEED" | "SUPPORTIVE" | "NONE" }
  | { type: "FEED" }
  | { type: "SKIP" }
  | { type: "CLIP_DONE" }
  | { type: "PROGRESS"; increased: boolean; growth: boolean }
  | { type: "DISMISS" };

/** Ten clip glTF (generate_capybara.py) ung voi tung trang thai. */
export const CLIP_CUA_TRANG_THAI: Record<CapyState, { clip: string; loop: boolean }> = {
  IDLE: { clip: "idle", loop: true },
  GREET: { clip: "greet", loop: false },
  TAP_REACT: { clip: "tap", loop: false },
  CURIOUS_WAIT: { clip: "curious", loop: true },
  READY_TO_FEED: { clip: "curious", loop: true },
  EATING: { clip: "eat", loop: false },
  HAPPY: { clip: "happy", loop: false },
  PROGRESS_TICK: { clip: "idle", loop: true },
  GROWTH_CELEBRATION: { clip: "celebrate", loop: false },
  SUPPORTIVE: { clip: "supportive", loop: true },
};

export function capyReducer(state: CapyState, ev: CapyEvent): CapyState {
  switch (ev.type) {
    case "GREET_TODAY":
      return state === "IDLE" ? "GREET" : state;
    case "TAP":
      // Chi phan ung khi dang ranh - khong cat ngang an/le lon len.
      return state === "IDLE" ? "TAP_REACT" : state;
    case "PHOTO_PENDING":
      return state === "IDLE" ? "CURIOUS_WAIT" : state;
    case "RESULT":
      if (ev.kind === "FEED") return "READY_TO_FEED";
      if (ev.kind === "SUPPORTIVE") return "SUPPORTIVE";
      return "IDLE";
    case "FEED":
      return state === "READY_TO_FEED" ? "EATING" : state;
    case "SKIP":
      return state === "SUPPORTIVE" || state === "GROWTH_CELEBRATION" ? state : "IDLE";
    case "CLIP_DONE":
      if (state === "EATING") return "HAPPY";
      if (state === "GREET" || state === "TAP_REACT") return "IDLE";
      return state; // HAPPY cho PROGRESS; celebrate cho DISMISS (ack)
    case "PROGRESS":
      if (state !== "HAPPY" && state !== "PROGRESS_TICK" && state !== "IDLE") return state;
      if (ev.growth) return "GROWTH_CELEBRATION";
      return ev.increased ? "PROGRESS_TICK" : "IDLE";
    case "DISMISS":
      return "IDLE";
  }
}
