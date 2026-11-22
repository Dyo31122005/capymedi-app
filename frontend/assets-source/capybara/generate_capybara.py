"""Sinh nhan vat Capybara Companion 3D cho CapyMedi (TASK-CAPY-21, ADR-0016).

Chay (Blender 4.2 LTS, headless):

    blender --background --factory-startup --python frontend/assets-source/capybara/generate_capybara.py -- \
        --out frontend/public/companion/3d [--stages 1,2,3,4] [--preview <thu-muc-render>]

Ket qua: capy-stage-<n>.glb (glTF 2.0 binary) cho tung giai doan.

Thiet ke (tham chieu: frontend/public/capy_vui.png, capy_chao.png - KHONG sua anh goc):
  - Than + dau la MOT khoi tron (hop cac ellipsoid qua voxel remesh), skin vao
    armature voi trong so mem o co -> nghieng dau khong bi gay khuc.
  - Mat, diem sang, mui, mom, ma hong, tai, tay, chan: phan cung, trong so 1.0
    vao bone tuong ung. Cac phan cung mau duoc gop thanh 1 mesh/material.
  - Mau long: thuoc tinh mau dinh (COLOR_0) - bung/mat sang hon, lung toi hon.
  - Animation: moi clip la 1 action cua armature (export_animation_mode=ACTIONS).
    Clip "blink" CHI dong vao bone mat; cac clip khac KHONG dong vao bone mat
    -> frontend phat blink chong len bat ky clip nao.

Toa do Blender: Z len, nhan vat nhin ve -Y (sau khi export glTF: Y len, nhin +Z).
Script tat dinh: chay lai cho cung hinh hoc (khong dung so ngau nhien).
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass

import bmesh
import bpy
from mathutils import Matrix, Vector

FPS = 30

# --- Bang mau (sRGB hex, lay tu anh tham chieu) ------------------------------

PALETTE = {
    "eye": "#13182b",
    "highlight": "#ffffff",
    "nose": "#3b2a25",
    "mouth": "#7a2e2e",
    "tongue": "#ef8f8f",
    "blush": "#f6928a",
    "paw": "#7a4e30",
    "ear_inner": "#8f5c38",
    "cap": "#fbfbfb",
    "cross": "#e5262b",
    "scarf": "#3fa7a3",
}


def srgb(hex_color: str) -> tuple[float, float, float, float]:
    """sRGB hex -> mau tuyen tinh (Blender luu base color tuyen tinh)."""
    h = hex_color.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


@dataclass(frozen=True)
class Stage:
    key: str
    body_c: tuple[float, float, float]
    body_r: tuple[float, float, float]
    head_c: tuple[float, float, float]
    head_r: tuple[float, float, float]
    fur: str
    fur_dark: str
    fur_light: str
    muzzle: str
    eye_scale: float
    accessory: str | None = None  # None | "scarf" | "cap"


STAGES = {
    1: Stage("capy-stage-1", (0, 0, 0.27), (0.33, 0.30, 0.27), (0, -0.03, 0.60), (0.40, 0.37, 0.35),
             "#dba06a", "#c4864f", "#efc898", "#b77f50", 1.22),
    2: Stage("capy-stage-2", (0, 0, 0.36), (0.43, 0.39, 0.36), (0, -0.04, 0.78), (0.45, 0.41, 0.38),
             "#cd8f55", "#ae723f", "#e8b986", "#a46c42", 1.0),
    3: Stage("capy-stage-3", (0, 0, 0.41), (0.47, 0.42, 0.41), (0, -0.05, 0.88), (0.46, 0.42, 0.39),
             "#c4874e", "#a46a38", "#e0b07c", "#9b653d", 0.95, "scarf"),
    4: Stage("capy-stage-4", (0, 0, 0.42), (0.48, 0.43, 0.42), (0, -0.05, 0.90), (0.47, 0.43, 0.40),
             "#bf834b", "#9d6536", "#dcab77", "#96613a", 0.92, "cap"),
}


# --- Hinh hoc co ban -----------------------------------------------------------


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = FPS


def ellipsoid_bm(center, radii, segs=24, rings=12) -> bmesh.types.BMesh:
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=1.0)
    m = Matrix.Translation(Vector(center)) @ Matrix.Diagonal((*radii, 1.0))
    bmesh.ops.transform(bm, matrix=m, verts=bm.verts)
    return bm


def surface_point(center, radii, direction, inset=0.0) -> Vector:
    """Diem tren be mat ellipsoid theo huong `direction` (lui vao `inset`)."""
    d = Vector(direction).normalized()
    t = 1.0 / math.sqrt(sum((d[i] / radii[i]) ** 2 for i in range(3)))
    return Vector(center) + d * (t - inset)


def mesh_object(name: str, bm: bmesh.types.BMesh) -> bpy.types.Object:
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    for poly in me.polygons:
        poly.use_smooth = True
    return obj


def apply_modifiers(obj: bpy.types.Object) -> None:
    deps = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(deps))
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    bpy.data.meshes.remove(old)


def material(name: str, color: str, roughness=0.75, emission: float = 0.0, vertex_color: bool = False):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = srgb(color)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if emission:
        bsdf.inputs["Emission Color"].default_value = srgb(color)
        bsdf.inputs["Emission Strength"].default_value = emission
    if vertex_color:
        node = mat.node_tree.nodes.new("ShaderNodeVertexColor")
        node.layer_name = "Col"
        mat.node_tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


# --- Nhan vat --------------------------------------------------------------------


class Builder:
    """Gom cac phan cung theo (material, bone) roi skin vao armature."""

    def __init__(self, st: Stage):
        self.st = st
        self.parts: list[tuple[bpy.types.Object, str, str]] = []  # (obj, material, bone)
        self.bones: dict[str, tuple[Vector, Vector, str | None]] = {}

    def part(self, name, bm, mat: str, bone: str) -> bpy.types.Object:
        obj = mesh_object(name, bm)
        self.parts.append((obj, mat, bone))
        return obj

    # ---- than + dau mot khoi -------------------------------------------------
    def blob(self) -> bpy.types.Object:
        st = self.st
        bm = ellipsoid_bm(st.body_c, st.body_r, 48, 24)
        neck_z = (st.body_c[2] + st.body_r[2] + st.head_c[2] - st.head_r[2]) / 2 + 0.03
        filler = ellipsoid_bm((0, st.head_c[1] * 0.5, neck_z), (st.body_r[0] * 0.93, st.body_r[1] * 0.92, 0.17))
        me_f = bpy.data.meshes.new("tmp_f")
        filler.to_mesh(me_f)
        filler.free()
        bm.from_mesh(me_f)
        bpy.data.meshes.remove(me_f)
        head = ellipsoid_bm(st.head_c, st.head_r, 48, 24)
        me_h = bpy.data.meshes.new("tmp_h")
        head.to_mesh(me_h)
        head.free()
        bm.from_mesh(me_h)
        bpy.data.meshes.remove(me_h)
        obj = mesh_object("Body", bm)
        rem = obj.modifiers.new("remesh", "REMESH")
        rem.mode = "VOXEL"
        rem.voxel_size = 0.016
        sm = obj.modifiers.new("smooth", "SMOOTH")
        sm.factor = 0.8
        sm.iterations = 12
        dec = obj.modifiers.new("decimate", "DECIMATE")
        dec.ratio = 0.11
        apply_modifiers(obj)
        for poly in obj.data.polygons:
            poly.use_smooth = True
        # Cat phan duoi day (z < 0.005) cho phang de dung vung tren san.
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        for v in bm.verts:
            if v.co.z < 0.005:
                v.co.z = 0.005
        bm.to_mesh(obj.data)
        bm.free()
        self._fur_colors(obj)
        return obj

    def _fur_colors(self, obj) -> None:
        st = self.st
        base, dark, light = (Vector(srgb(c)[:3]) for c in (st.fur, st.fur_dark, st.fur_light))
        me = obj.data
        attr = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
        top = st.head_c[2] + st.head_r[2]
        for i, v in enumerate(me.vertices):
            p = v.co
            front = max(0.0, min(1.0, (-p.y) / 0.4))  # mat truoc sang hon
            back = max(0.0, min(1.0, p.y / 0.4))
            high = max(0.0, min(1.0, (p.z - st.head_c[2]) / max(top - st.head_c[2], 1e-3)))
            c = base.lerp(light, 0.45 * front * (1 - high))
            c = c.lerp(dark, 0.55 * back + 0.25 * high)
            attr.data[i].color = (*c, 1.0)

    # ---- chi tiet khuon mat va chi -----------------------------------------
    def details(self) -> None:
        st = self.st
        hc, hr = Vector(st.head_c), Vector(st.head_r)
        # Mom: khoi bau duc nho ra phia truoc, nua tren gan dau, nua duoi (ham) gan jaw.
        mz_c = surface_point(hc, hr, (0, -1, -0.42), inset=0.055)
        mz_r = (hr.x * 0.46, hr.y * 0.26, hr.z * 0.36)
        upper = ellipsoid_bm(mz_c, mz_r)
        bmesh.ops.delete(upper, geom=[v for v in upper.verts if v.co.z < mz_c.z - mz_r[2] * 0.20], context="VERTS")
        self.part("MuzzleUpper", upper, "muzzle", "head")
        jaw_c = mz_c + Vector((0, 0.03, -mz_r[2] * 0.34))
        jaw = ellipsoid_bm(jaw_c, (mz_r[0] * 0.78, mz_r[1] * 0.92, mz_r[2] * 0.60))
        bmesh.ops.delete(jaw, geom=[v for v in jaw.verts if v.co.z > jaw_c.z + mz_r[2] * 0.12], context="VERTS")
        self.part("Jaw", jaw, "muzzle", "jaw")
        # Long mieng (toi) + luoi, lui vao trong de chi lo ra khi ha ham.
        mouth_c = mz_c + Vector((0, 0.05, -mz_r[2] * 0.30))
        self.part("Mouth", ellipsoid_bm(mouth_c, (mz_r[0] * 0.62, mz_r[1] * 0.70, mz_r[2] * 0.42)), "mouth", "head")
        self.part("Tongue", ellipsoid_bm(jaw_c + Vector((0, -0.01, mz_r[2] * 0.12)),
                                          (mz_r[0] * 0.42, mz_r[1] * 0.55, mz_r[2] * 0.16)), "tongue", "jaw")
        # Mui: rong, det, tren dinh mom.
        nose_c = mz_c + Vector((0, -mz_r[1] * 0.78, mz_r[2] * 0.55))
        self.part("Nose", ellipsoid_bm(nose_c, (mz_r[0] * 0.58, mz_r[1] * 0.42, mz_r[2] * 0.36)), "nose", "head")
        ph = nose_c + Vector((0, 0.006, -mz_r[2] * 0.50))
        self.part("Philtrum", ellipsoid_bm(ph, (0.008, 0.012, mz_r[2] * 0.20), 10, 6), "mouth", "head")
        self.bones["jaw"] = (jaw_c + Vector((0, 0.06, mz_r[2] * 0.25)), jaw_c + Vector((0, -0.08, 0)), "head")

        # Mat to, tron, bong - kem 2 diem sang.
        es = st.eye_scale
        for side, sx in (("L", 1), ("R", -1)):
            e_c = surface_point(hc, hr, (0.42 * sx, -1, 0.10), inset=0.035)
            e_r = (0.062 * es, 0.045 * es, 0.072 * es)
            self.part(f"Eye_{side}", ellipsoid_bm(e_c, e_r), "eye", f"eye_{side}")
            hl = e_c + Vector((0.022 * es * sx * -1, -e_r[1] * 0.9, e_r[2] * 0.42))
            self.part(f"EyeHi_{side}", ellipsoid_bm(hl, (0.018 * es, 0.01, 0.02 * es), 12, 8), "highlight", f"eye_{side}")
            hl2 = e_c + Vector((0.02 * es * sx, -e_r[1] * 0.92, -e_r[2] * 0.30))
            self.part(f"EyeHi2_{side}", ellipsoid_bm(hl2, (0.009 * es, 0.006, 0.01 * es), 10, 6), "highlight", f"eye_{side}")
            self.bones[f"eye_{side}"] = (e_c, e_c + Vector((0, -0.06, 0)), "head")
            # Ma hong.
            b_c = surface_point(hc, hr, (0.70 * sx, -1, -0.30), inset=0.012)
            self.part(f"Blush_{side}", ellipsoid_bm(b_c, (0.058, 0.02, 0.040), 20, 10), "blush", "head")
            # Tai: tron nho, toi hon, co long tai trong.
            ear_c = surface_point(hc, hr, (0.72 * sx, 0.15, 0.75), inset=0.02)
            self.part(f"Ear_{side}", ellipsoid_bm(ear_c, (0.105, 0.06, 0.095)), "fur_dark", f"ear_{side}")
            self.part(f"EarIn_{side}", ellipsoid_bm(ear_c + Vector((0, -0.03, -0.005)), (0.062, 0.03, 0.056), 16, 8),
                      "ear_inner", f"ear_{side}")
            self.bones[f"ear_{side}"] = (ear_c - Vector((0, 0, 0.05)), ear_c + Vector((0, 0, 0.04)), "head")

            # Tay ngan + ban tay toi mau.
            bc, br = Vector(st.body_c), Vector(st.body_r)
            sh = surface_point(bc, br, (0.80 * sx, -0.55, 0.42), inset=0.07)
            hand = sh + Vector((0.04 * sx, -0.07, -br.z * 0.42))
            arm_c = (sh + hand) / 2
            arm_len = (sh - hand).length
            arm = ellipsoid_bm(arm_c, (0.075, 0.075, arm_len * 0.62))
            self.part(f"Arm_{side}", arm, "fur", f"arm_{side}")
            self.part(f"Paw_{side}", ellipsoid_bm(hand, (0.075, 0.07, 0.06)), "paw", f"arm_{side}")
            self.bones[f"arm_{side}"] = (sh, hand, "body")
            # Chan: det, toi mau, nho ra phia truoc.
            foot = Vector((0.20 * sx * br.x / 0.45, -br.y * 0.70, 0.045))
            self.part(f"Foot_{side}", ellipsoid_bm(foot, (0.10 * br.x / 0.45, 0.12, 0.05)), "paw", "root")

        if st.accessory == "scarf":
            neck_z = st.head_c[2] - st.head_r[2] * 0.86  # duoi cam, tren vai
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, cap_ends=False, segments=40, radius1=1.0, radius2=1.0, depth=1.0)
            bmesh.ops.transform(bm, verts=bm.verts, matrix=Matrix.Translation((0, 0.0, neck_z))
                                @ Matrix.Diagonal((st.body_r[0] * 0.99, st.body_r[1] * 0.97, 0.075, 1)))
            bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.035)
            self.part("Scarf", bm, "scarf", "body")
            self.part("ScarfKnot", ellipsoid_bm((0.14, -st.body_r[1] * 0.98, neck_z - 0.03), (0.07, 0.045, 0.08)),
                      "scarf", "body")
        if st.accessory == "cap":
            top = Vector((0, st.head_c[1] + 0.02, st.head_c[2] + st.head_r[2] - 0.02))
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, cap_ends=True, segments=40, radius1=0.24, radius2=0.20, depth=0.16)
            bmesh.ops.transform(bm, verts=bm.verts, matrix=Matrix.Translation(top + Vector((0, 0, 0.06)))
                                @ Matrix.Diagonal((1.0, 0.82, 1.0, 1)))
            self.part("Cap", bm, "cap", "head")
            front = top + Vector((0, -0.205, 0.075))
            for size in ((0.075, 0.012, 0.024), (0.024, 0.012, 0.075)):
                bm = bmesh.new()
                bmesh.ops.create_cube(bm, size=1.0)
                bmesh.ops.transform(bm, verts=bm.verts, matrix=Matrix.Translation(front) @ Matrix.Diagonal((*size, 1)))
                self.part("Cross", bm, "cross", "head")

    # ---- armature ---------------------------------------------------------------
    def armature(self) -> bpy.types.Object:
        st = self.st
        arm_data = bpy.data.armatures.new("CapyRig")
        rig = bpy.data.objects.new("CapyRig", arm_data)
        bpy.context.scene.collection.objects.link(rig)
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode="EDIT")
        eb = arm_data.edit_bones
        neck = Vector((0, st.head_c[1] * 0.6, st.head_c[2] - st.head_r[2] * 0.75))
        base = {
            "root": (Vector((0, 0, 0)), Vector((0, 0, 0.12)), None),
            "body": (Vector((0, 0, 0.12)), neck, "root"),
            "head": (neck, Vector((0, st.head_c[1], st.head_c[2] + st.head_r[2])), "body"),
        }
        for name, (h, t, parent) in {**base, **self.bones}.items():
            b = eb.new(name)
            b.head, b.tail = h, t
            b.roll = 0.0
            if parent:
                b.parent = eb[parent]
        bpy.ops.object.mode_set(mode="OBJECT")
        return rig

    def assemble(self) -> bpy.types.Object:
        st = self.st
        body = self.blob()
        self.details()
        rig = self.armature()

        # Trong so mem cho khoi than/dau: chuyen tiep quanh co.
        neck_z = st.head_c[2] - st.head_r[2] * 0.75
        vg_body, vg_head = body.vertex_groups.new(name="body"), body.vertex_groups.new(name="head")
        for v in body.data.vertices:
            t = max(0.0, min(1.0, (v.co.z - (neck_z - 0.10)) / 0.22))
            w = t * t * (3 - 2 * t)
            vg_head.add([v.index], w, "REPLACE")
            vg_body.add([v.index], 1.0 - w, "REPLACE")
        body.data.materials.append(material("fur_body", st.fur, 0.85, vertex_color=True))

        # Phan cung: gan vertex group = bone, gop theo material.
        groups: dict[str, list[bpy.types.Object]] = {}
        for obj, mat, bone in self.parts:
            vg = obj.vertex_groups.new(name=bone)
            vg.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
            groups.setdefault(mat, []).append(obj)
        colors = {"fur": st.fur, "fur_dark": st.fur_dark, "muzzle": st.muzzle, **PALETTE}
        meshes = [body]
        for mat, objs in groups.items():
            rough = {"eye": 0.15, "highlight": 0.3, "nose": 0.35, "cap": 0.6}.get(mat, 0.8)
            emit = 1.5 if mat == "highlight" else 0.0
            m = material(mat, colors[mat], rough, emit)
            for o in objs:
                o.data.materials.append(m)
            with bpy.context.temp_override(active_object=objs[0], selected_editable_objects=objs):
                bpy.ops.object.join()
            objs[0].name = f"Part_{mat}"
            meshes.append(objs[0])

        for obj in meshes:
            obj.parent = rig
            mod = obj.modifiers.new("rig", "ARMATURE")
            mod.object = rig
        return rig


# --- Animation -------------------------------------------------------------------

# Truc local cua bone (roll = 0): bone huong +Z the gioi (body/head): X = X the gioi,
# Y = len, Z = -Y the gioi (huong mat). Bone huong ve phia truoc (eye/jaw): Y = huong mat.
DEG = math.pi / 180


def action(rig, name: str, keys: list[tuple[float, dict]], loop: bool = False) -> None:
    """keys: [(giay, {bone: {"loc": (x,y,z), "rot": (x,y,z) do, "scale": (x,y,z)}})]."""
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = act
    bones_used = {b for _, pose in keys for b in pose}
    for pb in rig.pose.bones:
        pb.rotation_mode = "XYZ"
    for sec, pose in keys:
        frame = 1 + round(sec * FPS)
        for bname in bones_used:
            pb = rig.pose.bones[bname]
            spec = pose.get(bname, {})
            pb.location = spec.get("loc", (0, 0, 0))
            pb.rotation_euler = tuple(a * DEG for a in spec.get("rot", (0, 0, 0)))
            pb.scale = spec.get("scale", (1, 1, 1))
            pb.keyframe_insert("location", frame=frame)
            pb.keyframe_insert("rotation_euler", frame=frame)
            pb.keyframe_insert("scale", frame=frame)
    for fc in act.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
            kp.easing = "AUTO"
    # Dua vao NLA de exporter thay va giu lai.
    track = rig.animation_data.nla_tracks.new()
    track.name = name
    track.strips.new(name, 1, act)
    rig.animation_data.action = None
    act["capy_loop"] = loop


def animations(rig, st: Stage) -> None:
    baby = st.key.endswith("1")
    amp = 1.25 if baby else 1.0

    def breathe(s):
        return {"body": {"scale": (1 + 0.012 * s, 1 + 0.02 * s, 1 + 0.012 * s)}}

    # IDLE: tho + lac dau nhe + vay tai (vong 4s, khong dong vao mat).
    action(rig, "idle", [
        (0.0, {**breathe(0), "head": {"rot": (0, 0, 0)}, "ear_L": {}, "ear_R": {}, "jaw": {"rot": (16, 0, 0)}}),
        (1.0, {**breathe(1), "head": {"rot": (-2, 3 * amp, 2 * amp)}, "ear_L": {}, "ear_R": {}, "jaw": {"rot": (16, 0, 0)}}),
        (2.0, {**breathe(0), "head": {"rot": (0, 0, 0)}, "ear_L": {"rot": (14, 0, 0)}, "ear_R": {}, "jaw": {"rot": (16, 0, 0)}}),
        (2.25, {**breathe(0.2), "head": {"rot": (0, 0, 0)}, "ear_L": {}, "ear_R": {}, "jaw": {"rot": (16, 0, 0)}}),
        (3.0, {**breathe(1), "head": {"rot": (-2, -3 * amp, -2 * amp)}, "ear_L": {}, "ear_R": {}, "jaw": {"rot": (16, 0, 0)}}),
        (4.0, {**breathe(0), "head": {"rot": (0, 0, 0)}, "ear_L": {}, "ear_R": {}, "jaw": {"rot": (16, 0, 0)}}),
    ], loop=True)

    closed = {"scale": (1, 1, 0.08)}
    action(rig, "blink", [
        (0.0, {"eye_L": {}, "eye_R": {}}),
        (0.07, {"eye_L": closed, "eye_R": closed}),
        (0.14, {"eye_L": closed, "eye_R": closed}),
        (0.24, {"eye_L": {}, "eye_R": {}}),
    ])

    up = 0.10 * amp
    action(rig, "greet", [
        (0.0, {"root": {}, "body": {}, "head": {}, "arm_R": {}, "jaw": {}}),
        (0.25, {"root": {"loc": (0, up, 0)}, "body": {}, "head": {"rot": (0, 0, 8)}, "arm_R": {"rot": (0, 0, 120)},
                "jaw": {"rot": (14, 0, 0)}}),
        (0.5, {"root": {}, "body": {}, "head": {"rot": (0, 0, 8)}, "arm_R": {"rot": (0, 0, 100)}, "jaw": {"rot": (14, 0, 0)}}),
        (0.75, {"root": {}, "body": {}, "head": {"rot": (0, 0, 8)}, "arm_R": {"rot": (0, 0, 130)}, "jaw": {"rot": (14, 0, 0)}}),
        (1.0, {"root": {}, "body": {}, "head": {"rot": (0, 0, 8)}, "arm_R": {"rot": (0, 0, 100)}, "jaw": {"rot": (14, 0, 0)}}),
        (1.5, {"root": {}, "body": {}, "head": {}, "arm_R": {}, "jaw": {}}),
    ])

    action(rig, "tap", [
        (0.0, {"root": {}, "body": {}, "head": {}, "ear_L": {}, "ear_R": {}}),
        (0.12, {"root": {}, "body": {"scale": (1.06, 0.9, 1.06)}, "head": {}, "ear_L": {}, "ear_R": {}}),
        (0.3, {"root": {"loc": (0, 0.08 * amp, 0)}, "body": {"scale": (0.97, 1.05, 0.97)}, "head": {"rot": (0, 0, -10)},
               "ear_L": {"rot": (20, 0, 0)}, "ear_R": {"rot": (20, 0, 0)}}),
        (0.5, {"root": {}, "body": {"scale": (1.03, 0.96, 1.03)}, "head": {"rot": (0, 0, -6)}, "ear_L": {}, "ear_R": {}}),
        (0.8, {"root": {}, "body": {}, "head": {}, "ear_L": {}, "ear_R": {}}),
    ])

    lean = {"rot": (-8, 0, 0)}
    action(rig, "curious", [
        (0.0, {"body": lean, "head": {"rot": (-6, 0, 12)}, "ear_L": {"rot": (10, 0, 0)}, "ear_R": {"rot": (10, 0, 0)}}),
        (1.0, {"body": lean, "head": {"rot": (-8, 4, 16)}, "ear_L": {"rot": (16, 0, 0)}, "ear_R": {"rot": (6, 0, 0)}}),
        (2.0, {"body": lean, "head": {"rot": (-6, 0, 12)}, "ear_L": {"rot": (10, 0, 0)}, "ear_R": {"rot": (10, 0, 0)}}),
    ], loop=True)

    action(rig, "eat", [
        (0.0, {"body": lean, "head": {"rot": (-6, 0, 0)}, "jaw": {}}),
        (0.3, {"body": {"rot": (-14, 0, 0)}, "head": {"rot": (-14, 0, 0)}, "jaw": {"rot": (30, 0, 0)}}),
        (0.55, {"body": {"rot": (-12, 0, 0)}, "head": {"rot": (-8, 0, 0)}, "jaw": {"rot": (2, 0, 0)}}),
        (0.75, {"body": {"rot": (-10, 0, 0)}, "head": {"rot": (-4, 0, 4)}, "jaw": {"rot": (16, 0, 0)}}),
        (0.95, {"body": {"rot": (-8, 0, 0)}, "head": {"rot": (-4, 0, -4)}, "jaw": {"rot": (2, 0, 0)}}),
        (1.15, {"body": {"rot": (-6, 0, 0)}, "head": {"rot": (-2, 0, 4)}, "jaw": {"rot": (16, 0, 0)}}),
        (1.35, {"body": {"rot": (-4, 0, 0)}, "head": {"rot": (-2, 0, -4)}, "jaw": {"rot": (2, 0, 0)}}),
        (1.55, {"body": {"rot": (-2, 0, 0)}, "head": {"rot": (0, 0, 2)}, "jaw": {"rot": (14, 0, 0)}}),
        (1.8, {"body": {}, "head": {}, "jaw": {}}),
    ])

    arms_up = {"arm_L": {"rot": (0, 0, -110)}, "arm_R": {"rot": (0, 0, 110)}}
    action(rig, "happy", [
        (0.0, {"root": {}, "body": {}, "head": {}, "jaw": {}, "arm_L": {}, "arm_R": {}}),
        (0.15, {"root": {}, "body": {"scale": (1.07, 0.9, 1.07)}, "head": {}, "jaw": {"rot": (18, 0, 0)}, "arm_L": {}, "arm_R": {}}),
        (0.4, {"root": {"loc": (0, 0.16 * amp, 0)}, "body": {}, "head": {"rot": (6, 0, 0)}, "jaw": {"rot": (22, 0, 0)}, **arms_up}),
        (0.65, {"root": {}, "body": {"scale": (1.05, 0.93, 1.05)}, "head": {}, "jaw": {"rot": (18, 0, 0)}, **arms_up}),
        (0.85, {"root": {"loc": (0, 0.07 * amp, 0)}, "body": {}, "head": {"rot": (0, 0, 6)}, "jaw": {"rot": (18, 0, 0)}, **arms_up}),
        (1.05, {"root": {}, "body": {}, "head": {"rot": (0, 0, -4)}, "jaw": {"rot": (12, 0, 0)}, "arm_L": {}, "arm_R": {}}),
        (1.4, {"root": {}, "body": {}, "head": {}, "jaw": {}, "arm_L": {}, "arm_R": {}}),
    ])

    action(rig, "celebrate", [
        (0.0, {"root": {}, "body": {}, "jaw": {}, "arm_L": {}, "arm_R": {}}),
        (0.2, {"root": {}, "body": {"scale": (1.1, 0.86, 1.1)}, "jaw": {"rot": (20, 0, 0)}, "arm_L": {}, "arm_R": {}}),
        (0.7, {"root": {"loc": (0, 0.28, 0), "rot": (0, 180, 0)}, "body": {"scale": (0.95, 1.08, 0.95)},
               "jaw": {"rot": (26, 0, 0)}, **arms_up}),
        (1.2, {"root": {"loc": (0, 0, 0), "rot": (0, 360, 0)}, "body": {"scale": (1.08, 0.9, 1.08)},
               "jaw": {"rot": (22, 0, 0)}, **arms_up}),
        (1.5, {"root": {"loc": (0, 0.08, 0), "rot": (0, 360, 0)}, "body": {}, "jaw": {"rot": (20, 0, 0)}, **arms_up}),
        (1.9, {"root": {"rot": (0, 360, 0)}, "body": {}, "jaw": {"rot": (10, 0, 0)}, "arm_L": {}, "arm_R": {}}),
        (2.4, {"root": {"rot": (0, 360, 0)}, "body": {}, "jaw": {}, "arm_L": {}, "arm_R": {}}),
    ])

    calm = {"arm_L": {"rot": (-20, 0, 15)}, "arm_R": {"rot": (-20, 0, -15)}}
    action(rig, "supportive", [
        (0.0, {"head": {"rot": (-4, 0, 6)}, "body": {}, **calm}),
        (1.5, {"head": {"rot": (-8, 0, 8)}, "body": {"scale": (1.01, 1.015, 1.01)}, **calm}),
        (3.0, {"head": {"rot": (-4, 0, 6)}, "body": {}, **calm}),
    ], loop=True)


# --- Xuat + preview ------------------------------------------------------------


def export_glb(path: str) -> None:
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        export_apply=False,
        export_yup=True,
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_force_sampling=True,
        export_optimize_animation_size=True,
        export_skins=True,
        export_all_influences=False,
        export_vertex_color="MATERIAL",
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
    )


def preview(rig, out_dir: str, st: Stage) -> None:
    """Render Cycles CPU vai tu the de kiem tra bang mat (khong dua vao repo)."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.render.resolution_x = scene.render.resolution_y = 420
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.82, 0.9, 1.0, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    scene.world = world
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    cam.location = (0.9, -3.2, 1.25)
    cam.rotation_euler = (math.radians(84), 0, math.radians(16))
    cam.data.lens = 50
    scene.camera = cam
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(40), math.radians(20), math.radians(-30))
    scene.collection.objects.link(sun)
    poses = [("idle", 0.0), ("blink", 0.1), ("eat", 0.3), ("happy", 0.4), ("greet", 0.25), ("supportive", 1.5)]
    for name, sec in poses:
        rig.animation_data.action = bpy.data.actions[name]
        scene.frame_set(1 + round(sec * FPS))
        scene.render.filepath = os.path.join(out_dir, f"{st.key}-{name}.png")
        bpy.ops.render.render(write_still=True)
    rig.animation_data.action = None


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--stages", default="1,2,3,4")
    ap.add_argument("--preview")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    for n in (int(x) for x in args.stages.split(",")):
        st = STAGES[n]
        reset_scene()
        rig = Builder(st).assemble()
        animations(rig, st)
        export_glb(os.path.join(args.out, f"{st.key}.glb"))
        if args.preview:
            os.makedirs(args.preview, exist_ok=True)
            preview(rig, args.preview, st)
        print(f"[capy] exported {st.key}")


if __name__ == "__main__":
    main()
