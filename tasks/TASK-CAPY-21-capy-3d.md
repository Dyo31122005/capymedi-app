# TASK-CAPY-21: Capy 3D (Blender → GLB → R3F) + máy trạng thái

**Domain:** `frontend`, `companion`
**Owner:** AI
**Sprint:** `[chưa xếp sprint]`
**Status:** In Review

Kế hoạch: [`planning/capybara-companion-implementation-plan.md`](../planning/capybara-companion-implementation-plan.md); [`ADR-0016`](../adrs/0016-capybara-companion-domain.md).

## Kết quả thực hiện (2026-11-14)

- **Asset:** `frontend/assets-source/capybara/generate_capybara.py` (Blender 4.2.3 LTS, `bpy`, tất định) sinh `frontend/public/companion/3d/capy-stage-{1..4}.glb` (khoảng 460–545 KB mỗi file, 12–15 nghìn tam giác, 1 skin, 9 clip). Đã soát bằng ảnh render Cycles và so với `capy_vui.png`/`capy_chao.png`.
- **Runtime:** `three` 0.181.2 + `@react-three/fiber` 9.8.2 (thêm qua pnpm). `capy-3d-scene.tsx` (AnimationMixer sở hữu bone, GSAP chỉ sở hữu group bọc ngoài và món ăn, lọc track blink, `frameloop` tạm dừng khi khuất màn hình), `capy-character.tsx` (`next/dynamic` với `ssr:false`, phát hiện WebGL, ErrorBoundary, xử lý mất context, fallback 2D, reduced-motion = tư thế tĩnh), `capy-machine.ts` (reducer thuần), `use-capy-behavior.ts`, `src/lib/companion-assets.ts` (registry).
- **Lỗi tìm ra khi test trên trình duyệt và đã sửa:** đổi thẻ bọc `<button>`/`<div>` làm remount Canvas; R3F gọi `forceContextLoss()` và 3D rơi về 2D. Sửa bằng cấu trúc DOM cố định và bỏ qua sự kiện mất context khi canvas đã rời DOM.
- Test: `npm run test:companion` (gồm cả việc đọc GLB thật để kiểm clip ứng với mọi trạng thái): **OK**.

## Definition of Done

Áp dụng [`ADR-0005`](../adrs/0005-definition-of-done.md). Chưa chạy `npm run build` hay full suite.
