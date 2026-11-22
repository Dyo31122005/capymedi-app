"use client";

// Sheet "Hanh trinh cua Capy" (TASK-CAPY-22): Capy lon, 4 giai doan, dat ten.

import { useState } from "react";
import { toast } from "sonner";
import { CapyPrimaryButton, CapySheet } from "@/components/capy/capy-ui";
import { renameCompanion, type CompanionState } from "@/lib/companion";
import { CAPY_STAGE_NAMES } from "@/lib/companion-assets";
import { CapyCharacter } from "./capy-character";
import { moTaTienDo, ProgressBar } from "./companion-card";
import { useCapyBehavior } from "./use-capy-behavior";

type Enabled = Extract<CompanionState, { enabled: true }>;

export function CompanionSheet({
  companion,
  accessToken,
  onClose,
  onUpdated,
}: {
  companion: Enabled;
  accessToken?: string | null;
  onClose: () => void;
  onUpdated: (c: CompanionState) => void;
}) {
  const { state, tap, clipDone } = useCapyBehavior();
  const [ten, setTen] = useState(companion.name ?? "");
  const [dangLuu, setDangLuu] = useState(false);

  const luuTen = async () => {
    setDangLuu(true);
    try {
      onUpdated(await renameCompanion(ten, accessToken));
      toast.success("Đã đặt tên cho Capy");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không đặt được tên");
    } finally {
      setDangLuu(false);
    }
  };

  return (
    <CapySheet onClose={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Hành trình của Capy">
        <CapyCharacter
          stage={companion.stage}
          state={state}
          onTap={tap}
          onClipDone={clipDone}
          label={`${companion.name || companion.stageLabel}, ${companion.stageLabel}`}
          className="mx-auto h-[210px] w-[210px]"
        />
        <p className="font-display m-0 mt-1 text-center text-[20px] font-extrabold text-[#16386E]">
          {companion.name || companion.stageLabel}
        </p>
        <p className="m-0 mt-1 text-center text-[13px] text-[#3D5D8C]">{moTaTienDo(companion)}</p>
        <div className="mt-2.5 rounded-full bg-[#CFE6FF] p-[3px]">
          <ProgressBar
            pct={companion.isMaxStage ? 100 : companion.progressPct}
            label={moTaTienDo(companion)}
          />
        </div>

        <ol className="mt-4 grid grid-cols-4 gap-2" aria-label="Các giai đoạn của Capy">
          {CAPY_STAGE_NAMES.map((name, i) => {
            const so = i + 1;
            const daQua = so < companion.stage;
            const hienTai = so === companion.stage;
            return (
              <li
                key={name}
                className={`rounded-[14px] px-1.5 py-2 text-center text-[11.5px] font-semibold leading-tight ${
                  hienTai
                    ? "bg-[#16386E] text-white"
                    : daQua
                      ? "bg-[#BFEBDC] text-[#14563F]"
                      : "bg-[#EDF0F6] text-[#8A96AD]"
                }`}
                aria-current={hienTai ? "step" : undefined}
              >
                {daQua ? "✓ " : ""}
                {name}
                {!daQua && !hienTai && (
                  <span className="mt-0.5 block text-[10.5px] font-medium">Sắp tới</span>
                )}
              </li>
            );
          })}
        </ol>

        <p className="m-0 mt-4 text-[13px] leading-[1.5] text-[#5B6A85]">
          Mỗi khi bạn xác nhận liều thuốc trong ngày, Capy được ăn một bữa và lớn dần. Capy không
          bao giờ ốm hay buồn vì bạn — ngày không có thuốc, Capy chỉ nghỉ ngơi.
        </p>

        <label className="mt-4 block text-[12.5px] font-semibold text-[#16386E]" htmlFor="capy-ten">
          Đặt tên cho Capy
        </label>
        <div className="mt-1.5 flex gap-2">
          <input
            id="capy-ten"
            value={ten}
            onChange={(e) => setTen(e.target.value)}
            maxLength={20}
            placeholder="Ví dụ: Bơ"
            className="min-h-[48px] flex-1 rounded-[16px] border border-[#D6DEEA] px-3.5 text-[15px] outline-none focus:border-[#16386E]"
          />
          <button
            type="button"
            onClick={luuTen}
            disabled={dangLuu || ten.trim().length === 0}
            className="min-h-[48px] rounded-[16px] bg-[#EDF0F6] px-4 text-[14px] font-semibold text-[#16386E] disabled:opacity-50"
          >
            Lưu
          </button>
        </div>
        <div className="mt-4">
          <CapyPrimaryButton onClick={onClose}>Đóng</CapyPrimaryButton>
        </div>
      </div>
    </CapySheet>
  );
}
