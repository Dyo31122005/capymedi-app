// ngayVN (2026-11-14): "hom nay" theo gio Viet Nam, khong phai ngay UTC.
// Chay: node --experimental-strip-types tests/vn-time.test.mts
import assert from "node:assert/strict";

import { ngayVN } from "../src/lib/vn-time.ts";

// 16:59:59 UTC = 23:59:59 gio VN -> van la ngay 14.
assert.equal(ngayVN(new Date("2026-11-14T16:59:59Z")), "2026-11-14");
// 17:00 UTC = 0h ngay 15 gio VN -> ngay 15 (toISOString().slice(0,10) cho ra 14).
assert.equal(ngayVN(new Date("2026-11-14T17:00:00Z")), "2026-11-15");
// 02:30 sang gio VN ngay 15 = 19:30 UTC ngay 14.
assert.equal(ngayVN(new Date("2026-11-14T19:30:00Z")), "2026-11-15");
// Dinh dang YYYY-MM-DD, co so 0 dang truoc.
assert.match(ngayVN(new Date("2026-01-05T03:00:00Z")), /^2026-01-05$/);

console.log("vn-time: 4 kiem tra deu dat");
