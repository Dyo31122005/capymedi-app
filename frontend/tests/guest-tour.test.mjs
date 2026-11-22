import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

// TASK-024 - nut "Tham quan". Kiem tra tinh tren source, giong auth-login-proxy.test.mjs.
const read = (p) => readFile(new URL(p, import.meta.url), "utf8");

const route = await read("../src/app/api/auth/guest-login/route.ts");
const component = await read("../src/components/auth/guest-tour.tsx");
const auth = await read("../src/lib/auth.tsx");
const loginForm = await read("../src/components/auth/login-form.tsx");
const mobileLogin = await read("../src/components/auth/mobile-login.tsx");

// Frontend khong bao gio biet email/mat khau tai khoan khach.
for (const [name, src] of [
  ["route", route],
  ["component", component],
  ["auth", auth],
]) {
  assert.doesNotMatch(
    src,
    /capymedi\.dev|password\s*:\s*["']/i,
    `${name} must not embed guest credentials`,
  );
}

// BFF: chi chuyen tiep role hop le, refresh_token vao httpOnly cookie, khong tra ve client.
assert.match(route, /body\?\.role !== "doctor" && body\?\.role !== "patient"/);
assert.match(route, /JSON\.stringify\(\{ role: body\.role \}\)/);
assert.match(
  route,
  /cookieStore\.set\(REFRESH_COOKIE_NAME, refreshToken, REFRESH_COOKIE_OPTIONS\)/,
);
assert.match(route, /const \{ refresh_token: refreshToken, \.\.\.clientSafeData \} = data/);
assert.match(route, /status:\s*503/);
// GET loi mang -> coi nhu tat, khong lam vo trang dang nhap.
assert.match(route, /catch\s*\{\s*return NextResponse\.json\(\{ enabled: false, roles: \[\] \}\)/s);

// Component an hoan toan khi backend tat / khong co role nao.
assert.match(component, /if \(roles\.length === 0\) return null;/);
assert.match(component, /fetch\("\/api\/auth\/guest-login"/);
assert.match(auth, /loginAsGuest/);

// Co mat o ca ban desktop lan mobile.
assert.match(loginForm, /<GuestTour \/>/);
assert.match(mobileLogin, /<GuestTour variant="mobile" \/>/);

console.log("guest tour tests passed");
