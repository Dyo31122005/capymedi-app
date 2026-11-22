"use client";

// Scene 3D cua Capy (TASK-CAPY-21) - CHI chay o client (nap qua next/dynamic
// ssr:false trong capy-character.tsx), khong dong toi WebGL luc SSR.
//
// Quyen so huu animation:
//   - AnimationMixer (clip glTF) so huu MOI bone cua nhan vat.
//   - GSAP chi so huu `wrap` (group boc ngoai: nhay nhe khi tien do tang, chuyen
//     giai doan) va group mon an. Khong he thong nao ghi transform cua he kia.
// Exporter glTF lay mau MOI bone cho MOI clip, nen o day loc track: "blink" chi
// giu track bone mat; cac clip khac bo track bone mat -> blink chong len duoc.

import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import gsap from "gsap";
import { Suspense, useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";
import type { CapyFood } from "@/lib/care-moment";
import { CLIP_CUA_TRANG_THAI, type CapyState } from "./capy-machine";

const LA_TRACK_MAT = (t: THREE.KeyframeTrack) => /^eye_[LR]\./.test(t.name);

function chuanBiClip(clips: THREE.AnimationClip[]): Map<string, THREE.AnimationClip> {
  const out = new Map<string, THREE.AnimationClip>();
  for (const c of clips) {
    const tracks =
      c.name === "blink" ? c.tracks.filter(LA_TRACK_MAT) : c.tracks.filter((t) => !LA_TRACK_MAT(t));
    out.set(c.name, new THREE.AnimationClip(c.name, c.duration, tracks));
  }
  return out;
}

type ModelProps = {
  url: string;
  state: CapyState;
  reducedMotion: boolean;
  tick: number;
  onClipDone: () => void;
};

function CapyModel({ url, state, reducedMotion, tick, onClipDone }: ModelProps) {
  const gltf = useLoader(GLTFLoader, url);
  const scene = useMemo(() => cloneSkinned(gltf.scene), [gltf]);
  const clips = useMemo(() => chuanBiClip(gltf.animations), [gltf]);
  const mixer = useMemo(() => new THREE.AnimationMixer(scene), [scene]);
  const wrap = useRef<THREE.Group>(null);
  const current = useRef<THREE.AnimationAction | null>(null);
  const doneRef = useRef(onClipDone);
  const invalidate = useThree((s) => s.invalidate);

  useEffect(() => {
    doneRef.current = onClipDone;
  }, [onClipDone]);

  // Vat lieu: giu mau tu GLB, chi lam mem va nhan hon cho phong cach sticker.
  useEffect(() => {
    scene.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      mesh.frustumCulled = false; // mesh skinned: bounding box tinh tu rest pose
      const m = mesh.material as THREE.MeshStandardMaterial;
      if (m && "roughness" in m) m.envMapIntensity = 0;
    });
  }, [scene]);

  // Chuyen clip theo trang thai.
  useEffect(() => {
    const spec = CLIP_CUA_TRANG_THAI[state];
    const clip = clips.get(spec.clip);
    if (!clip) return;
    const action = mixer.clipAction(clip);
    action.reset();
    action.setLoop(spec.loop ? THREE.LoopRepeat : THREE.LoopOnce, spec.loop ? Infinity : 1);
    action.clampWhenFinished = !spec.loop;
    const prev = current.current;
    if (reducedMotion) {
      // Khong chuyen dong: dat tu the tinh (frame dau cua idle) va bao xong ngay.
      mixer.stopAllAction();
      const rest = mixer.clipAction(clips.get("idle")!);
      rest.reset().play();
      mixer.update(0);
      rest.paused = true;
      current.current = rest;
      invalidate();
      if (!spec.loop) queueMicrotask(() => doneRef.current());
      return;
    }
    action.play();
    if (prev && prev !== action) prev.crossFadeTo(action, 0.25, false);
    current.current = action;
    const onFinished = (e: { action: THREE.AnimationAction }) => {
      if (e.action === action) doneRef.current();
    };
    mixer.addEventListener("finished", onFinished);
    return () => mixer.removeEventListener("finished", onFinished);
  }, [state, clips, mixer, reducedMotion, invalidate]);

  // Chop mat ngau nhien 2.5-6s (khong khi an / le / dong chuyen dong).
  useEffect(() => {
    if (reducedMotion) return;
    const blink = clips.get("blink");
    if (!blink) return;
    const action = mixer.clipAction(blink);
    action.setLoop(THREE.LoopOnce, 1);
    let timer: ReturnType<typeof setTimeout>;
    const lich = () => {
      timer = setTimeout(
        () => {
          if (state !== "EATING" && state !== "GROWTH_CELEBRATION") action.reset().play();
          lich();
        },
        2500 + Math.random() * 3500,
      );
    };
    lich();
    return () => clearTimeout(timer);
  }, [clips, mixer, reducedMotion, state]);

  // GSAP: nhay nhe group boc ngoai khi tien do tang (PROGRESS_TICK).
  useEffect(() => {
    if (!wrap.current || reducedMotion || tick === 0) return;
    const g = wrap.current;
    const tl = gsap.timeline();
    tl.to(g.scale, { x: 1.08, y: 1.08, z: 1.08, duration: 0.18, ease: "power2.out" }).to(g.scale, {
      x: 1,
      y: 1,
      z: 1,
      duration: 0.6,
      ease: "elastic.out(1, 0.45)",
    });
    return () => {
      tl.kill();
      g.scale.set(1, 1, 1);
    };
  }, [tick, reducedMotion]);

  useEffect(
    () => () => {
      mixer.stopAllAction();
      mixer.uncacheRoot(scene);
    },
    [mixer, scene],
  );

  useFrame((_, dt) => {
    if (!reducedMotion) mixer.update(Math.min(dt, 0.1));
  });

  return (
    <group ref={wrap}>
      <primitive object={scene} />
    </group>
  );
}

const MAU_MON_AN: Record<CapyFood, { main: string; accent: string }> = {
  leaf: { main: "#6dbb5a", accent: "#3f8f3a" },
  watermelon: { main: "#ff6b6b", accent: "#3fa34d" },
  orange: { main: "#ffa53b", accent: "#3f8f3a" },
};

/** Mon an ao (trai cay/la) - dung bang hinh hoc three, KHONG BAO GIO la thuoc. */
function FoodItem({
  food,
  eating,
  reducedMotion,
}: {
  food: CapyFood;
  eating: boolean;
  reducedMotion: boolean;
}) {
  const g = useRef<THREE.Group>(null);
  const c = MAU_MON_AN[food];
  useEffect(() => {
    const obj = g.current;
    if (!obj) return;
    if (reducedMotion) {
      obj.visible = !eating;
      return;
    }
    const ctx = gsap.context(() => {
      if (!eating) {
        obj.visible = true;
        obj.position.set(0.55, 0.35, 0.55);
        obj.scale.setScalar(0);
        gsap.to(obj.scale, { x: 1, y: 1, z: 1, duration: 0.45, ease: "back.out(2)" });
        gsap.to(obj.position, {
          y: 0.45,
          duration: 0.9,
          yoyo: true,
          repeat: -1,
          ease: "sine.inOut",
        });
        gsap.to(obj.rotation, { y: Math.PI * 2, duration: 4, repeat: -1, ease: "none" });
      } else {
        gsap.killTweensOf(obj.position);
        gsap.to(obj.position, { x: 0, y: 0.62, z: 0.42, duration: 0.35, ease: "power2.in" });
        gsap.to(obj.scale, {
          x: 0,
          y: 0,
          z: 0,
          duration: 0.3,
          delay: 0.3,
          ease: "power2.in",
          onComplete: () => {
            obj.visible = false;
          },
        });
      }
    });
    return () => ctx.revert();
  }, [eating, food, reducedMotion]);

  return (
    <group ref={g} position={[0.55, 0.4, 0.55]}>
      {food === "watermelon" ? (
        <>
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.13, 0.13, 0.06, 24, 1, false, 0, Math.PI]} />
            <meshStandardMaterial color={c.main} roughness={0.6} />
          </mesh>
          <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, 0, -0.001]} scale={[1.08, 1.08, 1.02]}>
            <cylinderGeometry args={[0.13, 0.13, 0.055, 24, 1, true, 0, Math.PI]} />
            <meshStandardMaterial color={c.accent} roughness={0.7} side={THREE.DoubleSide} />
          </mesh>
        </>
      ) : food === "orange" ? (
        <>
          <mesh>
            <sphereGeometry args={[0.11, 24, 16]} />
            <meshStandardMaterial color={c.main} roughness={0.55} />
          </mesh>
          <mesh position={[0.03, 0.11, 0]} rotation={[0, 0, -0.6]} scale={[1, 0.35, 0.6]}>
            <sphereGeometry args={[0.05, 12, 8]} />
            <meshStandardMaterial color={c.accent} roughness={0.7} />
          </mesh>
        </>
      ) : (
        <mesh rotation={[0, 0, 0.5]} scale={[1, 0.25, 0.55]}>
          <sphereGeometry args={[0.14, 20, 12]} />
          <meshStandardMaterial color={c.main} roughness={0.6} />
        </mesh>
      )}
    </group>
  );
}

export type Capy3DSceneProps = {
  url: string;
  state: CapyState;
  food: CapyFood | null;
  reducedMotion: boolean;
  /** Tang 1 moi lan tien do tang -> GSAP nhay nhe group boc ngoai. */
  progressTick: number;
  active: boolean;
  frameHeight: number;
  onClipDone: () => void;
  onContextLost: () => void;
};

export default function Capy3DScene(p: Capy3DSceneProps) {
  // Khung hinh theo chieu cao model -> moi giai doan deu vua khung, giu ty le lon dan.
  const camY = p.frameHeight * 0.52;
  const camZ = p.frameHeight * 2.6 + 0.5;
  return (
    <Canvas
      dpr={[1, 1.75]}
      frameloop={p.active && !p.reducedMotion ? "always" : "demand"}
      camera={{ position: [0, camY + 0.15, camZ], fov: 30, near: 0.1, far: 20 }}
      gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
      onCreated={({ gl, camera }) => {
        camera.lookAt(0, camY, 0);
        const canvas = gl.domElement;
        canvas.addEventListener("webglcontextlost", (e) => {
          e.preventDefault();
          // R3F goi forceContextLoss() khi unmount - luc do canvas da roi DOM,
          // khong phai mat context that -> bo qua.
          setTimeout(() => {
            if (canvas.isConnected) p.onContextLost();
          }, 0);
        });
      }}
      style={{ pointerEvents: "none" }}
      aria-hidden
    >
      <hemisphereLight args={["#fff7ec", "#c9b39b", 1.5]} />
      <directionalLight position={[1.5, 3, 2.5]} intensity={2.2} color="#fff3e2" />
      <directionalLight position={[-2, 1.5, -1]} intensity={0.7} color="#d8e8ff" />
      <Suspense fallback={null}>
        <CapyModel
          url={p.url}
          state={p.state}
          reducedMotion={p.reducedMotion}
          tick={p.progressTick}
          onClipDone={p.onClipDone}
        />
        {p.food &&
          (p.state === "CURIOUS_WAIT" || p.state === "READY_TO_FEED" || p.state === "EATING") && (
            <FoodItem food={p.food} eating={p.state === "EATING"} reducedMotion={p.reducedMotion} />
          )}
      </Suspense>
    </Canvas>
  );
}
