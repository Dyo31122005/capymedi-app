"use client";

// Lop phu sau mot lan xac nhan lieu (TASK-CAPY-23, planning §3.2 / §5.8).
//
//  - FEED: mon an ao -> cham de cho an (tu an sau 3s) -> an -> vui -> lay tien do
//    THAT tu backend (GET /companion/me) -> nhich thanh tien do -> neu co
//    pending_celebration_stage thi le lon len + ack (idempotent o backend).
//  - SUPPORTIVE: anh khong khop het luot - Capy binh than, khong mon an, khong an mung.
//  - GROWTH: mo thang le lon len (vd mo app khi Capy da lon trong luc vang mat).
//
// Frontend KHONG cong tien do: man nay chi trinh bay ket qua backend da tinh.
// Moi nut deu bo qua duoc; dong lop phu khong anh huong gi toi ho so lieu.

import { useCallback, useEffect, useRef, useState } from "react";
import { CapyPrimaryButton, CapySecondaryButton } from "@/components/capy/capy-ui";
import {
  ackCelebration,
  getCompanion,
  sendCompanionEvent,
  type CompanionState,
} from "@/lib/companion";
import type { CapyFood } from "@/lib/care-moment";
import { CapyCharacter, usePrefersReducedMotion } from "./capy-character";
import { ProgressBar } from "./companion-card";
import { useCapyBehavior } from "./use-capy-behavior";

type Enabled = Extract<CompanionState, { enabled: true }>;

const AUTO_FEED_MS = 3000;
const TEN_MON: Record<CapyFood, string> = {
  leaf: "lá cỏ non",
  watermelon: "miếng dưa hấu",
  orange: "quả quýt",
};
const BUA: Record<CapyFood, string> = {
  leaf: "Bữa sáng",
  watermelon: "Bữa trưa",
  orange: "Bữa tối",
};

export type CareMomentProps = {
  kind: "FEED" | "SUPPORTIVE" | "GROWTH";
  companion: Enabled;
  food?: CapyFood;
  /** Dong thong tin lieu vua xac nhan (gio, ten thuoc) - giu tu man "Xong rồi!" cu. */
  infoLine?: string;
  pointsAwarded?: number;
  /** SUPPORTIVE: co nguoi than dang cho duyet anh khong. */
  awaitingCaregiver?: boolean;
  accessToken?: string | null;
  onClose: (latest: CompanionState | null) => void;
  /** QA-03: anh sai het luot, KHONG co nguoi than -> benh nhan co the xac nhan
   *  ro rang "da uong" (tu khai). Chi luc do Capy moi duoc tinh. */
  onExplicitConfirm?: () => Promise<void>;
};

export function CareMoment(p: CareMomentProps) {
  const reducedMotion = usePrefersReducedMotion();
  const initial =
    p.kind === "FEED"
      ? "READY_TO_FEED"
      : p.kind === "SUPPORTIVE"
        ? "SUPPORTIVE"
        : "GROWTH_CELEBRATION";
  const { state, send, clipDone } = useCapyBehavior(initial);
  // undefined = chua co ket qua backend; null = lay tien do that bai.
  const [latest, setLatest] = useState<Enabled | null | undefined>(
    p.kind === "GROWTH" ? p.companion : undefined,
  );
  const [happyDone, setHappyDone] = useState(false);
  const [tick, setTick] = useState(0);
  const [dangXacNhan, setDangXacNhan] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const closed = useRef(false);
  const shownGrowth = useRef(false);

  const dong = useCallback(
    (ket: CompanionState | null) => {
      if (closed.current) return;
      closed.current = true;
      p.onClose(ket);
    },
    [p],
  );

  // Focus nut chinh moi khi doi buoc (khong bay focus: lop phu dong la tra lai trang).
  useEffect(() => {
    box.current
      ?.querySelector<HTMLButtonElement>("[data-primary] button, button[data-primary]")
      ?.focus();
  }, [state]);

  // Focus + Esc (Esc = bo qua, khong anh huong ho so lieu).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (state === "READY_TO_FEED") sendCompanionEvent("FEED_SKIP", p.accessToken);
        dong(latest ?? null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state, latest, dong, p.accessToken]);

  useEffect(() => {
    if (p.kind === "SUPPORTIVE") sendCompanionEvent("SUPPORTIVE_SHOWN", p.accessToken);
  }, [p.kind, p.accessToken]);

  const choAn = useCallback(
    (cach: "FEED_TAP" | "FEED_AUTO") => {
      if (state !== "READY_TO_FEED") return;
      sendCompanionEvent(cach, p.accessToken);
      send({ type: "FEED" });
      // Lay tien do THAT song song voi animation an.
      getCompanion(p.accessToken)
        .then((c) => setLatest(c.enabled ? c : null))
        .catch(() => setLatest(null));
    },
    [state, send, p.accessToken],
  );

  // Tu cho an sau 3s neu nguoi dung khong cham.
  useEffect(() => {
    if (state !== "READY_TO_FEED") return;
    const t = setTimeout(() => choAn("FEED_AUTO"), AUTO_FEED_MS);
    return () => clearTimeout(t);
  }, [state, choAn]);

  const onClipDone = useCallback(() => {
    if (state === "HAPPY") setHappyDone(true);
    else clipDone();
  }, [state, clipDone]);

  // Sau khi vui xong + co ket qua backend -> nhich tien do / le lon len.
  useEffect(() => {
    if (state !== "HAPPY" || !happyDone || latest === undefined) return;
    if (latest === null) {
      // Khong lay duoc tien do (mang loi) -> ve binh thuong, tien do se cap nhat lan tai sau.
      send({ type: "PROGRESS", increased: false, growth: false });
      return;
    }
    const tang = latest.stage > p.companion.stage || latest.progressPct > p.companion.progressPct;
    if (tang) setTick((n) => n + 1);
    send({ type: "PROGRESS", increased: tang, growth: latest.pendingCelebrationStage != null });
  }, [state, happyDone, latest, p.companion, send]);

  useEffect(() => {
    if (state === "GROWTH_CELEBRATION" && !shownGrowth.current) {
      shownGrowth.current = true;
      sendCompanionEvent("GROWTH_SEEN", p.accessToken);
    }
  }, [state, p.accessToken]);

  const xacNhanLonLen = async () => {
    const c = latest ?? p.companion;
    if (c.pendingCelebrationStage != null) {
      // Idempotent o backend; loi mang -> le se hien lai lan sau (khong mat gi).
      await ackCelebration(c.pendingCelebrationStage, p.accessToken).catch(() => false);
    }
    dong({ ...c, pendingCelebrationStage: null });
  };

  const hienThi = latest ?? p.companion;
  const dangLonLen = state === "GROWTH_CELEBRATION";
  const stageHienThi =
    dangLonLen && hienThi.pendingCelebrationStage
      ? hienThi.pendingCelebrationStage
      : p.companion.stage;
  const mon = p.food ?? "leaf";

  let tieuDe: string;
  let moTa: string;
  if (p.kind === "SUPPORTIVE") {
    tieuDe = "Capy ở đây với bạn";
    moTa = p.awaitingCaregiver
      ? "Ảnh chưa khớp đơn thuốc. Người thân sẽ xem giúp bạn. Nếu không chắc đã uống đúng thuốc, hãy hỏi bác sĩ hoặc dược sĩ."
      : "Ảnh chưa khớp đơn thuốc. Nếu bạn chắc chắn đã uống đúng thuốc, hãy bấm xác nhận bên dưới; nếu không chắc, hãy hỏi bác sĩ hoặc dược sĩ.";
  } else if (dangLonLen) {
    tieuDe = `Capy đã lớn thành ${hienThi.stageLabel}!`;
    moTa =
      p.kind === "GROWTH"
        ? "Capy đã lớn trong lúc bạn vắng. Cảm ơn bạn đã chăm sóc mình!"
        : "Cảm ơn bạn đã chăm sóc mình mỗi ngày.";
  } else if (state === "READY_TO_FEED") {
    tieuDe = `${BUA[mon]} của Capy`;
    moTa = `Cảm ơn bạn đã ghi lại liều thuốc. Chạm để cho Capy ăn ${TEN_MON[mon]} nhé!`;
  } else if (state === "EATING") {
    tieuDe = "Capy đang ăn…";
    moTa = "Ngon quá!";
  } else {
    tieuDe = "Capy no rồi! 💛";
    moTa =
      hienThi.isMaxStage || !hienThi.nextStageLabel
        ? `${hienThi.stageLabel} đã trưởng thành.`
        : `Capy lớn thêm một chút · ${hienThi.progressPct}% đến ${hienThi.nextStageLabel}`;
  }

  const nen =
    p.kind === "SUPPORTIVE" ? "bg-[#EAF2FB]" : dangLonLen ? "bg-[#FFF1C9]" : "bg-[#BFEBDC]";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="care-moment-title"
      ref={box}
      className={`absolute inset-0 z-50 flex flex-col items-center justify-center overflow-hidden p-7 text-center ${nen}`}
    >
      <CapyCharacter
        stage={stageHienThi}
        state={state}
        food={p.kind === "FEED" ? mon : null}
        progressTick={tick}
        onClipDone={onClipDone}
        onTap={state === "READY_TO_FEED" ? () => choAn("FEED_TAP") : undefined}
        label={tieuDe}
        className="h-[260px] w-[260px] max-w-full"
      />
      <h2
        id="care-moment-title"
        className="font-display m-0 mt-2 text-[24px] font-extrabold leading-[1.2] text-[#14385E]"
      >
        {tieuDe}
      </h2>
      <p
        className="m-0 mt-2 max-w-[320px] text-[15px] leading-[1.5] text-[#2F4F6E]"
        aria-live="polite"
      >
        {moTa}
      </p>
      {p.infoLine && <p className="m-0 mt-1.5 text-[12.5px] text-[#3F5F70]">{p.infoLine}</p>}

      {p.kind !== "SUPPORTIVE" && !dangLonLen && state !== "READY_TO_FEED" && (
        <div className="mt-3 w-full max-w-[280px]">
          <ProgressBar
            pct={hienThi.isMaxStage ? 100 : hienThi.progressPct}
            label={`Tiến độ của Capy ${hienThi.progressPct}%`}
          />
        </div>
      )}
      {p.pointsAwarded != null && p.pointsAwarded > 0 && p.kind === "FEED" && (
        <p className="m-0 mt-2 rounded-full bg-white/70 px-3 py-1 text-[12.5px] font-semibold text-[#14563F]">
          +{p.pointsAwarded} điểm thưởng
        </p>
      )}

      <div className="mt-6 flex w-full max-w-[320px] flex-col gap-2.5">
        {state === "READY_TO_FEED" ? (
          <>
            <div data-primary className="contents">
              <CapyPrimaryButton onClick={() => choAn("FEED_TAP")}>Cho Capy ăn</CapyPrimaryButton>
            </div>
            <CapySecondaryButton
              onClick={() => {
                sendCompanionEvent("FEED_SKIP", p.accessToken);
                dong(null);
              }}
            >
              Bỏ qua
            </CapySecondaryButton>
          </>
        ) : dangLonLen ? (
          <div data-primary className="contents">
            <CapyPrimaryButton onClick={xacNhanLonLen}>Tuyệt quá!</CapyPrimaryButton>
          </div>
        ) : (
          <>
            <div data-primary className="contents">
              <CapyPrimaryButton onClick={() => dong(latest ?? null)}>
                {p.kind === "SUPPORTIVE" ? "Đã hiểu" : "Về Hôm nay"}
              </CapyPrimaryButton>
            </div>
            {p.kind === "SUPPORTIVE" && !p.awaitingCaregiver && p.onExplicitConfirm && (
              <CapySecondaryButton
                disabled={dangXacNhan}
                onClick={async () => {
                  setDangXacNhan(true);
                  try {
                    await p.onExplicitConfirm?.();
                  } finally {
                    setDangXacNhan(false);
                  }
                }}
              >
                Tôi đã uống thuốc này
              </CapySecondaryButton>
            )}
          </>
        )}
      </div>
      {reducedMotion && (
        <span className="sr-only">Hiệu ứng chuyển động đang tắt theo cài đặt của bạn.</span>
      )}
    </div>
  );
}
