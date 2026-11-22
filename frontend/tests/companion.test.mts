import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  chonLoaiManHinh,
  daChoAn,
  danhDauDaChoAn,
  monAnTheoBuoi,
} from "../src/lib/care-moment.ts";
import { CLIP_CUA_TRANG_THAI, capyReducer, type CapyState } from "../src/components/companion/capy-machine.ts";

// --- CareMoment (TASK-CAPY-23, planning §3.2) ---------------------------------
const now = new Date(2026, 10, 14, 10, 0);
const homNay = new Date(2026, 10, 14, 8, 0).toISOString();
const homQua = new Date(2026, 10, 13, 8, 0).toISOString();
const base = { scheduledAt: homNay, now };

assert.equal(chonLoaiManHinh({ ...base, source: "PHOTO", resultStatus: "TAKEN", matched: true }), "FEED");
assert.equal(chonLoaiManHinh({ ...base, source: "PHOTO", resultStatus: "DELAYED", matched: true }), "FEED");
// Anh khong khop het luot -> KHONG BAO GIO FEED (co nguoi than -> AWAITING; khong co -> TAKEN 70% LP).
assert.equal(
  chonLoaiManHinh({ ...base, source: "PHOTO", resultStatus: "AWAITING_CAREGIVER", matched: false, nextAction: "CAREGIVER_REVIEW" }),
  "SUPPORTIVE",
);
assert.equal(
  chonLoaiManHinh({ ...base, source: "PHOTO", resultStatus: "TAKEN", matched: false, nextAction: "CAREGIVER_REVIEW" }),
  "SUPPORTIVE",
);
assert.equal(chonLoaiManHinh({ ...base, source: "PHOTO", resultStatus: "PENDING", matched: false, nextAction: "RETAKE" }), null);
assert.equal(chonLoaiManHinh({ ...base, source: "PHOTO", resultStatus: "PENDING", matched: null }), null);
// HTTP 200 nhung status khong phai da uong -> khong FEED.
assert.equal(chonLoaiManHinh({ ...base, source: "PHOTO", resultStatus: "PENDING", matched: true }), null);
assert.equal(chonLoaiManHinh({ ...base, source: "SELF_REPORT", resultStatus: "TAKEN" }), "FEED");
assert.equal(chonLoaiManHinh({ ...base, source: "SELF_REPORT", resultStatus: "MISSED" }), "NEUTRAL");
assert.equal(chonLoaiManHinh({ ...base, source: "SELF_REPORT", resultStatus: "AWAITING_CAREGIVER" }), "SUPPORTIVE");
assert.equal(chonLoaiManHinh({ source: "SELF_REPORT", resultStatus: "DELAYED", scheduledAt: homQua, now }), "NEUTRAL");

assert.equal(monAnTheoBuoi(new Date(2026, 10, 14, 8).toISOString()), "leaf");
assert.equal(monAnTheoBuoi(new Date(2026, 10, 14, 12).toISOString()), "watermelon");
assert.equal(monAnTheoBuoi(new Date(2026, 10, 14, 20).toISOString()), "orange");

// --- fedSlotIds: khong phat lai cho cung lieu, reset sang ngay moi, chiu loi storage ---
const map = new Map<string, string>();
const kho = { getItem: (k: string) => map.get(k) ?? null, setItem: (k: string, v: string) => void map.set(k, v) };
assert.equal(daChoAn("d1", now, kho), false);
danhDauDaChoAn("d1", now, kho);
danhDauDaChoAn("d1", now, kho);
assert.equal(daChoAn("d1", now, kho), true);
assert.deepEqual(JSON.parse(map.get("capy-fed-slots")!).ids, ["d1"]);
assert.equal(daChoAn("d1", new Date(2026, 10, 15, 9), kho), false, "ngay moi");
const hong = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
assert.equal(daChoAn("d1", now, hong), false);
danhDauDaChoAn("d1", now, hong); // khong throw
assert.equal(daChoAn("d1", now, null), false);

// --- State machine (planning §5.8) ---------------------------------------------
const run = (s: CapyState, ...evs: Parameters<typeof capyReducer>[1][]) => evs.reduce(capyReducer, s);
assert.equal(run("IDLE", { type: "GREET_TODAY" }, { type: "CLIP_DONE" }), "IDLE");
assert.equal(run("IDLE", { type: "TAP" }), "TAP_REACT");
assert.equal(run("EATING", { type: "TAP" }), "EATING", "cham khong cat ngang luc an");
// Luong cho an day du -> lon len.
assert.equal(
  run("IDLE", { type: "PHOTO_PENDING" }, { type: "RESULT", kind: "FEED" }, { type: "FEED" }, { type: "CLIP_DONE" },
      { type: "PROGRESS", increased: true, growth: true }),
  "GROWTH_CELEBRATION",
);
assert.equal(run("HAPPY", { type: "PROGRESS", increased: true, growth: false }), "PROGRESS_TICK");
assert.equal(run("HAPPY", { type: "PROGRESS", increased: false, growth: false }), "IDLE");
assert.equal(run("GROWTH_CELEBRATION", { type: "CLIP_DONE" }), "GROWTH_CELEBRATION", "cho ack, khong tu dong");
assert.equal(run("GROWTH_CELEBRATION", { type: "DISMISS" }), "IDLE");
assert.equal(run("READY_TO_FEED", { type: "SKIP" }), "IDLE");
assert.equal(run("IDLE", { type: "RESULT", kind: "SUPPORTIVE" }), "SUPPORTIVE");
assert.equal(run("SUPPORTIVE", { type: "FEED" }), "SUPPORTIVE", "SUPPORTIVE khong bao gio chuyen sang an");
assert.equal(run("SUPPORTIVE", { type: "DISMISS" }), "IDLE");
// Moi trang thai deu co clip THAT trong tung file GLB da export (doc chunk JSON cua GLB).
for (const stage of [1, 2, 3, 4]) {
  const buf = readFileSync(new URL(`../public/companion/3d/capy-stage-${stage}.glb`, import.meta.url));
  assert.equal(buf.toString("ascii", 0, 4), "glTF");
  const json = JSON.parse(buf.toString("utf8", 20, 20 + buf.readUInt32LE(12)));
  const clips = new Set<string>(json.animations.map((a: { name: string }) => a.name));
  assert.ok(clips.has("blink"), `stage ${stage} thieu blink`);
  for (const [s, c] of Object.entries(CLIP_CUA_TRANG_THAI)) assert.ok(clips.has(c.clip), `stage ${stage}: ${s} -> ${c.clip}`);
  assert.ok(json.meshes.length > 0 && json.skins.length === 1);
}

console.log("companion tests OK");
