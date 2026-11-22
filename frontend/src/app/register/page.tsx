"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  HeartPulse,
  Lock,
  Mail,
  ShieldCheck,
  User,
  UserCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { GoogleSignInButton } from "@/components/google-sign-in-button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";

export default function RegisterPage() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [registeredEmail, setRegisteredEmail] = useState("");
  // Gui lai email xac minh (Supabase auth.resend) - cho 60s giua 2 lan, Supabase
  // cung tu gioi han tan suat o phia may chu.
  const [choGuiLai, setChoGuiLai] = useState(0);
  const [dangGuiLai, setDangGuiLai] = useState(false);
  const [thongBaoGuiLai, setThongBaoGuiLai] = useState("");

  useEffect(() => {
    if (choGuiLai <= 0) return;
    const t = setTimeout(() => setChoGuiLai((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [choGuiLai]);

  const guiLaiEmail = async () => {
    const { createClient } = await import("@/lib/supabase");
    const supabase = createClient();
    if (!supabase || !registeredEmail) return;
    setDangGuiLai(true);
    setThongBaoGuiLai("");
    try {
      const { error: resendError } = await supabase.auth.resend({
        type: "signup",
        email: registeredEmail,
        options: { emailRedirectTo: `${window.location.origin}/auth/verify-email` },
      });
      if (resendError) throw resendError;
      setThongBaoGuiLai("Đã gửi lại email xác minh. Vui lòng kiểm tra hộp thư.");
      setChoGuiLai(60);
    } catch (err) {
      setThongBaoGuiLai(dichLoiEmail(err));
    } finally {
      setDangGuiLai(false);
    }
  };

  const { register: authRegister } = useAuth();
  const { login: protoLogin } = useProto();
  const router = useRouter();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!fullName.trim() || !email.trim() || !password.trim()) {
      setError("Vui lòng nhập đầy đủ thông tin bắt buộc.");
      return;
    }
    if (password.length < 8) {
      setError("Mật khẩu phải có ít nhất 8 ký tự.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Mật khẩu xác nhận không khớp.");
      return;
    }

    setError("");
    setLoading(true);

    try {
      let supabaseUid: string | undefined;

      // 1. Dang ky qua Supabase de gui email xac minh. Supabase Auth la NOI
      // DUY NHAT gui email (SMTP cau hinh trong Supabase project) - backend
      // KHONG gui mail. Truoc day thieu cau hinh thi bo qua im lang, van tao tai
      // khoan backend chua xac minh va bao "da gui email" -> nguoi dung ket vinh
      // vien (dang nhap bi chan, khong co email nao). Gio dung han va bao loi.
      const { createClient } = await import("@/lib/supabase");
      const supabase = createClient();
      if (!supabase) {
        throw new Error(
          "Hệ thống chưa cấu hình dịch vụ gửi email xác minh. Vui lòng liên hệ quản trị viên.",
        );
      }

      {
        const redirectTo = `${window.location.origin}/auth/verify-email`;
        const { data: sbData, error: sbError } = await supabase.auth.signUp({
          email: email.trim(),
          password,
          options: {
            data: { full_name: fullName.trim() },
            emailRedirectTo: redirectTo,
          },
        });

        if (sbError) {
          throw sbError;
        }
        // Supabase tra user voi identities rong (khong gui mail) khi email da
        // dang ky truoc do - khong bao "da gui email" sai su that.
        if (sbData.user && sbData.user.identities?.length === 0) {
          throw new Error(
            'Email này đã được đăng ký. Vui lòng đăng nhập hoặc dùng "Quên mật khẩu".',
          );
        }

        supabaseUid = sbData.user?.id;
      }

      // 2. Tao ban ghi tai khoan backend (is_email_verified = false)
      await authRegister({
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        role: "patient",
        provider_account_id: supabaseUid,
      });

      setRegisteredEmail(email.trim());
      setChoGuiLai(60);
    } catch (err) {
      setError(dichLoiEmail(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="grid min-h-screen bg-background lg:grid-cols-2">
      {/* Left side banner */}
      <div className="relative overflow-hidden bg-gradient-to-br from-primary/10 via-background to-accent/30 px-6 py-12 sm:px-12 lg:py-16">
        <div className="pointer-events-none absolute -left-16 -bottom-16 h-64 w-64 rounded-full bg-primary/20 blur-3xl" />
        <div className="relative mx-auto max-w-lg">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-primary transition-colors mb-6"
          >
            <ArrowLeft className="h-4 w-4" /> Quay lại trang chủ
          </Link>

          <div className="flex items-center gap-3">
            <Image
              src="/logo-capymedi-v2.png"
              alt="CapyMedi"
              width={72}
              height={72}
              className="h-14 w-14 shrink-0 sm:h-16 sm:w-16"
              priority
            />
            <p className="text-2xl font-extrabold tracking-tight sm:text-3xl">CapyMedi</p>
          </div>

          <div className="mt-6 inline-flex items-center rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
            Tạo tài khoản mới
          </div>

          <h1 className="mt-4 text-3xl font-extrabold leading-tight tracking-tight sm:text-4xl">
            Bắt đầu hành trình chăm sóc sức khỏe chủ động
          </h1>
          <p className="mt-4 text-base text-muted-foreground">
            Đăng ký tài khoản để theo dõi lịch uống thuốc, nhận nhắc nhở đúng giờ và kết nối trực
            tiếp với bác sĩ chuyên khoa.
          </p>

          <div className="mt-10 space-y-4 rounded-2xl border bg-card/50 p-6 backdrop-blur">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="mt-1 h-5 w-5 text-primary shrink-0" />
              <div>
                <h3 className="font-semibold text-sm">Nhắc nhở thông minh 3 cấp độ</h3>
                <p className="text-xs text-muted-foreground">
                  Thông báo, cuộc gọi tự động & cảnh báo người thân.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-1 h-5 w-5 text-primary shrink-0" />
              <div>
                <h3 className="font-semibold text-sm">Bác sĩ duyệt phác đồ (HITL)</h3>
                <p className="text-xs text-muted-foreground">
                  An toàn tối đa với sự đồng hành của chuyên gia y tế.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <HeartPulse className="mt-1 h-5 w-5 text-primary shrink-0" />
              <div>
                <h3 className="font-semibold text-sm">Tự động hoá theo dõi tuân thủ</h3>
                <p className="text-xs text-muted-foreground">
                  Xác minh hình ảnh và báo cáo nhiệt kế tuân thủ hàng ngày.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Right side form */}
      <div className="flex flex-col justify-center px-6 py-12 sm:px-12 lg:px-16">
        <div className="mx-auto w-full max-w-md space-y-6">
          {registeredEmail ? (
            <div className="space-y-6 rounded-2xl border bg-card/60 p-6 text-center backdrop-blur sm:p-8">
              <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400">
                <Mail className="h-7 w-7" />
              </div>
              <div className="space-y-2">
                <h2 className="text-2xl font-bold tracking-tight">Kiểm tra hộp thư của bạn</h2>
                <p className="text-sm text-muted-foreground">
                  Chúng tôi đã gửi email xác minh đến{" "}
                  <span className="font-semibold text-foreground">{registeredEmail}</span>. Vui lòng
                  nhấp vào liên kết trong email để kích hoạt tài khoản.
                </p>
              </div>

              <div className="rounded-lg bg-muted/60 p-3 text-xs text-muted-foreground text-left space-y-1">
                <p className="font-semibold text-foreground">💡 Lưu ý:</p>
                <p>• Kiểm tra cả thư mục Spam/Thư rác nếu không thấy email trong Hộp thư đến.</p>
                <p>• Sau khi nhấp liên kết xác minh, bạn có thể đăng nhập ngay vào hệ thống.</p>
              </div>

              <div className="space-y-2">
                <Button
                  type="button"
                  variant="outline"
                  className="w-full"
                  disabled={dangGuiLai || choGuiLai > 0}
                  onClick={guiLaiEmail}
                >
                  {dangGuiLai
                    ? "Đang gửi lại…"
                    : choGuiLai > 0
                      ? `Gửi lại email sau ${choGuiLai}s`
                      : "Gửi lại email xác minh"}
                </Button>
                {thongBaoGuiLai && (
                  <p className="text-xs text-muted-foreground" role="status">
                    {thongBaoGuiLai}
                  </p>
                )}
              </div>

              <div className="pt-2">
                <Link
                  href="/login"
                  className="inline-flex w-full items-center justify-center rounded-lg bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
                >
                  Quay lại trang Đăng nhập
                </Link>
              </div>
            </div>
          ) : (
            <>
              <div>
                <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">Tạo tài khoản mới</h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  Nhập thông tin cá nhân của bạn để đăng ký
                </p>
              </div>

              <form onSubmit={submit} className="space-y-4">
                {error && (
                  <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-3 text-sm font-medium text-destructive">
                    {error}
                  </div>
                )}

                <div className="space-y-2">
                  <Label htmlFor="full_name">Họ và tên</Label>
                  <div className="relative">
                    <User
                      aria-hidden="true"
                      className="absolute left-3 top-3 h-4 w-4 text-muted-foreground"
                    />
                    <Input
                      id="full_name"
                      placeholder="Nguyễn Văn A"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      className="pl-9"
                      required
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <div className="relative">
                    <Mail
                      aria-hidden="true"
                      className="absolute left-3 top-3 h-4 w-4 text-muted-foreground"
                    />
                    <Input
                      id="email"
                      type="email"
                      placeholder="name@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="pl-9"
                      required
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Vai trò</Label>
                  {/* SUA 2026-08-17 (yeu cau PM): bo Select vai tro - tu dang ky
                  CHI tao duoc tai khoan `patient` (benh nhan/nguoi than dung
                  chung role nay). Tai khoan bac si/admin chi do admin tao qua
                  account-api (specs/api-contracts.md §1b). */}
                  <div className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2.5 text-sm">
                    <UserCheck className="h-4 w-4 text-primary shrink-0" />
                    <span className="font-medium">Bệnh nhân / Người thân</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Tài khoản Bác sĩ phụ trách do quản trị viên cấp, không thể tự đăng ký.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password">Mật khẩu</Label>
                  <div className="relative">
                    <Lock
                      aria-hidden="true"
                      className="absolute left-3 top-3 h-4 w-4 text-muted-foreground"
                    />
                    <Input
                      id="password"
                      type="password"
                      placeholder="Tối thiểu 8 ký tự"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="pl-9"
                      required
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="confirm_password">Xác nhận mật khẩu</Label>
                  <div className="relative">
                    <Lock
                      aria-hidden="true"
                      className="absolute left-3 top-3 h-4 w-4 text-muted-foreground"
                    />
                    <Input
                      id="confirm_password"
                      type="password"
                      placeholder="Nhập lại mật khẩu"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      className="pl-9"
                      required
                    />
                  </div>
                </div>

                <Button
                  type="submit"
                  className="w-full h-11 text-base font-semibold"
                  disabled={loading}
                >
                  {loading ? "Đang đăng ký..." : "Đăng ký tài khoản"}
                </Button>
              </form>

              {/* Cung 1 nut voi trang dang nhap: Google khong phan biet dang
              nhap/dang ky - email chua ton tai thi backend tao tai khoan
              `patient` moi (backend/api/auth_routes.py::oauth_google). */}
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <span className="h-px flex-1 bg-border" />
                  <span className="text-xs font-medium text-muted-foreground">hoặc</span>
                  <span className="h-px flex-1 bg-border" />
                </div>
                <GoogleSignInButton label="Đăng ký bằng Google" />
              </div>

              <p className="text-center text-sm text-muted-foreground">
                Đã có tài khoản?{" "}
                <Link href="/login" className="font-semibold text-primary hover:underline">
                  Đăng nhập ngay
                </Link>
              </p>
            </>
          )}
        </div>
      </div>
    </main>
  );
}

// Loi tu Supabase Auth (tieng Anh) -> cau tieng Viet; khong bao thanh cong khi
// may chu email that bai.
function dichLoiEmail(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err ?? "");
  const status = (err as { status?: number } | null)?.status;
  if (/error sending (confirmation|recovery|magic link)? ?email|smtp/i.test(msg)) {
    return "Không gửi được email xác minh do lỗi máy chủ email. Vui lòng thử lại sau ít phút.";
  }
  if (status === 429 || /rate limit|too many|security purposes/i.test(msg)) {
    return "Bạn đã yêu cầu gửi email quá nhiều lần. Vui lòng đợi một lúc rồi thử lại.";
  }
  if (/already registered|already exists/i.test(msg)) {
    return 'Email này đã được đăng ký. Vui lòng đăng nhập hoặc dùng "Quên mật khẩu".';
  }
  return msg || "Đăng ký thất bại.";
}
