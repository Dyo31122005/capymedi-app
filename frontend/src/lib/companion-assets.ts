// Registry asset cua Capybara Companion (TASK-CAPY-21). MOI duong dan asset
// Capy nam o day - thay art/model cuoi cung chi can sua file nay.
//
// GLB sinh tu frontend/assets-source/capybara/generate_capybara.py (Blender 4.2).
// Fallback 2D (khong WebGL / mat context / loi tai model) dung sticker co san.

export type CapyStageAsset = {
  stage: number;
  key: string;
  glb: string;
  fallback: string;
  fallbackAlt: string;
  /** Ty le hien thi tuong doi giua cac giai doan (model da co kich thuoc that). */
  frameHeight: number;
};

export const CAPY_STAGE_ASSETS: Record<number, CapyStageAsset> = {
  1: {
    stage: 1,
    key: "CAPY_SO_SINH",
    glb: "/companion/3d/capy-stage-1.glb",
    fallback: "/capy_chao.png",
    fallbackAlt: "Capy sơ sinh đang vẫy chào",
    frameHeight: 1.0,
  },
  2: {
    stage: 2,
    key: "CAPY_CON",
    glb: "/companion/3d/capy-stage-2.glb",
    fallback: "/capy_vui.png",
    fallbackAlt: "Capy con đang vui",
    frameHeight: 1.25,
  },
  3: {
    stage: 3,
    key: "CAPY_NHO",
    glb: "/companion/3d/capy-stage-3.glb",
    fallback: "/capy_ngau.png",
    fallbackAlt: "Capy nhỡ đeo khăn",
    frameHeight: 1.35,
  },
  4: {
    stage: 4,
    key: "CAPY_Y_TA",
    glb: "/companion/3d/capy-stage-4.glb",
    fallback: "/capy_camon.png",
    fallbackAlt: "Capy y tá đội mũ y tá",
    frameHeight: 1.45,
  },
};

export const CAPY_SUPPORTIVE_FALLBACK = "/capy_yeu.png";

export function capyAsset(stage: number): CapyStageAsset {
  return CAPY_STAGE_ASSETS[stage] ?? CAPY_STAGE_ASSETS[1];
}

/** Ten hien thi 4 giai doan cho sheet hanh trinh (nhan that luon lay tu backend). */
export const CAPY_STAGE_NAMES = ["Capy sơ sinh", "Capy con", "Capy nhỡ", "Capy y tá"] as const;
