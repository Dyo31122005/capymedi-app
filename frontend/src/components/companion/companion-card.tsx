"use client";

// The Capy tren trang Hom nay (TASK-CAPY-22). Moi con so tien do do backend
// tra ve (GET /companion/me) - the chi hien thi.

import { useEffect } from "react";
import type { Dose } from "@/lib/doses";
import type { CompanionState } from "@/lib/companion";
import { monAnTheoBuoi } from "@/lib/care-moment";
import { CapyCharacter } from "./capy-character";
import { daChaoHomNay, useCapyBehavior } from "./use-capy-behavior";

type Enabled = Extract<CompanionState, { enabled: true }>;

const ICON_MON: Record<string, string> = { leaf: "🍃", watermelon: "🍉", orange: "🍊" };

export function iconBuaAn(d: Dose): { icon: string; label: string } {
  if (d.status === "TAKEN" || d.status === "DELAYED")
    return { icon: ICON_MON[monAnTheoBuoi(d.scheduledAt)], label: "đã ăn" };
  if (d.status === "AWAITING_CAREGIVER")
    return { icon: "⏳", label: "đang chờ người thân xem ảnh" };
  return { icon: "○", label: "chưa tới bữa" };
}

export function ProgressBar({ pct, label }: { pct: number; label: string }) {
  return (
    <div className="w-full">
      <div
        className="h-[8px] w-full overflow-hidden rounded-full bg-white/70"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-label={label}
      >
        <div
          className="h-full rounded-full bg-[#16386E] transition-[width] duration-700 ease-out motion-reduce:transition-none"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function moTaTienDo(c: Enabled): string {
  return c.isMaxStage || !c.nextStageLabel
    ? `${c.stageLabel} đã trưởng thành`
    : `Capy đang lớn · ${c.progressPct}% đến ${c.nextStageLabel}`;
}

export function CompanionCard({
  companion,
  dosesHomNay,
  onOpen,
  paused,
  progressTick,
}: {
  companion: Enabled;
  dosesHomNay: Dose[];
  onOpen: () => void;
  /** Mot lop phu khac dang dung WebGL -> the tam dung 3D (tranh 2 context). */
  paused: boolean;
  progressTick: number;
}) {
  const { state, send, tap, clipDone } = useCapyBehavior();
  useEffect(() => {
    if (!daChaoHomNay()) send({ type: "GREET_TODAY" });
  }, [send]);
  const ten = companion.name || companion.stageLabel;

  return (
    <div className="flex items-center gap-3.5 rounded-[28px] bg-[#CFE6FF] p-4">
      <CapyCharacter
        stage={companion.stage}
        state={state}
        onTap={tap}
        onClipDone={clipDone}
        progressTick={progressTick}
        forceFallback={paused}
        label={`${ten}, ${companion.stageLabel}`}
        className="h-[118px] w-[104px] shrink-0"
      />
      <div className="min-w-0 flex-1">
        <p className="font-display m-0 truncate text-[16px] font-bold leading-[1.3] text-[#16386E]">
          {ten}
        </p>
        <p className="m-0 mt-0.5 text-[12.5px] leading-[1.4] text-[#3D5D8C]">
          {moTaTienDo(companion)}
        </p>
        <div className="mt-2">
          <ProgressBar
            pct={companion.isMaxStage ? 100 : companion.progressPct}
            label={moTaTienDo(companion)}
          />
        </div>
        {dosesHomNay.length > 0 && (
          <p
            className="m-0 mt-2 flex flex-wrap items-center gap-1 text-[15px]"
            aria-label="Bữa của Capy hôm nay"
          >
            {dosesHomNay.map((d) => {
              const b = iconBuaAn(d);
              return (
                <span key={d.id} title={b.label} aria-label={b.label}>
                  {b.icon}
                </span>
              );
            })}
          </p>
        )}
        <button
          type="button"
          onClick={onOpen}
          className="mt-1.5 min-h-[32px] text-[12.5px] font-semibold text-[#16386E] underline-offset-2 hover:underline"
        >
          Hành trình của Capy →
        </button>
      </div>
    </div>
  );
}
