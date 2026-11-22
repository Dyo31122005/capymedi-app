# Capybara Companion — nguồn asset 3D

Nguồn duy nhất của các model `frontend/public/companion/3d/capy-stage-{1..4}.glb` là script
[`generate_capybara.py`](./generate_capybara.py) (Blender + `bpy`, tất định). **Không sửa GLB bằng tay**:
sửa script rồi sinh lại. Ảnh tham chiếu (`frontend/public/capy_vui.png`, `capy_chao.png`) giữ nguyên.

## Sinh lại

```bash
# Blender 4.2 LTS (đã kiểm chứng với 4.2.3), chạy từ gốc repo
blender --background --factory-startup \
  --python frontend/assets-source/capybara/generate_capybara.py -- \
  --out frontend/public/companion/3d --stages 1,2,3,4 [--preview <thư-mục-tạm-ngoài-repo>]
```

`--preview` render vài tư thế bằng Cycles CPU để soát bằng mắt. **Không commit ảnh preview.**

Sau khi sinh lại, chạy `npm run test:companion` (trong `frontend/`) để kiểm tra GLB đủ clip cho mọi trạng thái.

## Cấu trúc model

- Armature `CapyRig`, gồm các bone `root`, `body`, `head`, `jaw`, `eye_L/R`, `ear_L/R`, `arm_L/R`. Thân và đầu là một khối liền (voxel remesh), skin mềm ở cổ; các phần còn lại cứng theo bone.
- Clip glTF: `idle`, `blink`, `greet`, `tap`, `curious`, `eat`, `happy`, `celebrate`, `supportive`.
- Exporter lấy mẫu **mọi bone cho mọi clip**. Runtime (`src/components/companion/capy-3d-scene.tsx`) lọc lại: `blink` chỉ giữ track bone mắt, các clip khác bỏ track bone mắt, nhờ vậy chớp mắt chồng được lên mọi clip.
- Giai đoạn 3 có khăn, giai đoạn 4 có mũ y tá chữ thập đỏ. Đây là **asset sinh thủ tục**, chưa phải art cuối; thay art thì chỉ cần sửa [`src/lib/companion-assets.ts`](../../src/lib/companion-assets.ts).
