"use client";

// Capy 3D co fallback 2D (TASK-CAPY-21). Ban 3D chi la lop trinh bay: moi luong
// thuoc (xac nhan, ghi lieu) KHONG phu thuoc vao viec 3D tai duoc hay khong.
//
// Fallback 2D khi: trinh duyet khong co WebGL, mat context, tai GLB loi.
// Reduced motion: van hien model 3D nhung o tu the tinh, khong chuyen dong.

import dynamic from "next/dynamic";
import Image from "next/image";
import { Component, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { capyAsset, CAPY_SUPPORTIVE_FALLBACK } from "@/lib/companion-assets";
import type { CapyFood } from "@/lib/care-moment";
import type { CapyState } from "./capy-machine";

const Capy3DScene = dynamic(() => import("./capy-3d-scene"), { ssr: false, loading: () => null });

class ErrorBoundary extends Component<
  { fallback: ReactNode; onError: () => void; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onError();
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function coWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return Boolean(c.getContext("webgl2") ?? c.getContext("webgl"));
  } catch {
    return false;
  }
}

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const on = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

export type CapyCharacterProps = {
  stage: number;
  state: CapyState;
  food?: CapyFood | null;
  progressTick?: number;
  onClipDone?: () => void;
  onTap?: () => void;
  /** Mo ta cho trinh doc man hinh (vd "Capy con đang ăn lá"). */
  label: string;
  className?: string;
  /** Tat 3D (vd khi mot lop phu khac dang dung WebGL) - hien fallback 2D. */
  forceFallback?: boolean;
};

export function CapyCharacter({
  stage,
  state,
  food = null,
  progressTick = 0,
  onClipDone,
  onTap,
  label,
  className = "",
  forceFallback = false,
}: CapyCharacterProps) {
  const asset = capyAsset(stage);
  const reducedMotion = usePrefersReducedMotion();
  const [webgl, setWebgl] = useState<boolean | null>(null);
  const [failed, setFailed] = useState(false);
  const [visible, setVisible] = useState(true);
  const box = useRef<HTMLDivElement>(null);
  const doneRef = useRef(onClipDone);

  useEffect(() => {
    doneRef.current = onClipDone;
  }, [onClipDone]);
  useEffect(() => setWebgl(coWebGL()), []);

  // Tam dung render khi khuat man hinh hoac tab an.
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    let inView = true;
    const capNhat = () => setVisible(inView && document.visibilityState === "visible");
    const io = new IntersectionObserver(([e]) => {
      inView = e.isIntersecting;
      capNhat();
    });
    io.observe(el);
    document.addEventListener("visibilitychange", capNhat);
    return () => {
      io.disconnect();
      document.removeEventListener("visibilitychange", capNhat);
    };
  }, []);

  const daXong = useCallback(() => doneRef.current?.(), []);
  const dung3D = webgl === true && !failed && !forceFallback;
  // Fallback 2D khong co clip: bao "xong" ngay de may trang thai khong ket.
  useEffect(() => {
    if (!dung3D && webgl !== null) {
      const t = setTimeout(daXong, reducedMotion ? 0 : 600);
      return () => clearTimeout(t);
    }
  }, [dung3D, webgl, state, daXong, reducedMotion]);

  const fallback = (
    <Image
      src={state === "SUPPORTIVE" ? CAPY_SUPPORTIVE_FALLBACK : asset.fallback}
      alt=""
      fill
      sizes="240px"
      className="object-contain"
    />
  );

  // Cau truc DOM CO DINH (khong doi <button>/<div> theo onTap): doi the boc se
  // remount Canvas, R3F goi forceContextLoss() va 3D bi tat oan.
  return (
    <div ref={box} className={`relative ${className}`} data-capy-render={dung3D ? "3d" : "2d"}>
      {dung3D ? (
        <ErrorBoundary fallback={fallback} onError={() => setFailed(true)}>
          <Capy3DScene
            url={asset.glb}
            state={state}
            food={food}
            reducedMotion={reducedMotion}
            progressTick={progressTick}
            active={visible}
            frameHeight={asset.frameHeight}
            onClipDone={daXong}
            onContextLost={() => setFailed(true)}
          />
        </ErrorBoundary>
      ) : webgl === null ? null : (
        fallback
      )}
      <span className="sr-only" aria-live="polite">
        {label}
      </span>
      {onTap && (
        <button
          type="button"
          onClick={onTap}
          aria-label={`${label}. Chạm để chơi với Capy`}
          className="absolute inset-0 touch-manipulation rounded-[24px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#16386E]"
        />
      )}
    </div>
  );
}
