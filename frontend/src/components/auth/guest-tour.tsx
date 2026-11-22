"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Compass, Stethoscope, UserRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth, type GuestRole } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";
import { cn } from "@/lib/utils";

// TASK-024 - khoi "Tham quan" tren trang dang nhap: chon Bac si hoac Benh nhan,
// vao thang tai khoan khach do admin tao san. Backend quyet dinh co bat hay
// khong (GET /api/auth/guest-login) - tat thi khoi nay an hoan toan.
const ROLE_LABELS: Record<GuestRole, { label: string; icon: typeof Stethoscope }> = {
  doctor: { label: "Bác sĩ", icon: Stethoscope },
  patient: { label: "Bệnh nhân", icon: UserRound },
};

export function GuestTour({ variant = "desktop" }: { variant?: "desktop" | "mobile" }) {
  const [roles, setRoles] = useState<GuestRole[]>([]);
  const [pending, setPending] = useState<GuestRole | null>(null);
  const [error, setError] = useState("");
  const { loginAsGuest } = useAuth();
  const { login: protoLogin, pushActivity } = useProto();
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    fetch("/api/auth/guest-login", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : { enabled: false, roles: [] }))
      .then((data) => {
        if (!cancelled && data?.enabled && Array.isArray(data.roles)) {
          setRoles(
            data.roles.filter((r: string): r is GuestRole => r === "doctor" || r === "patient"),
          );
        }
      })
      .catch(() => {
        // Loi mang -> khong hien khoi tham quan, khong chan dang nhap thuong.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (roles.length === 0) return null;

  const start = async (role: GuestRole) => {
    setError("");
    setPending(role);
    try {
      const u = await loginAsGuest(role);
      // Giong luong dang nhap thuong (app/login/page.tsx::submit).
      protoLogin(u.role as GuestRole, u.full_name);
      pushActivity(
        "Chế độ tham quan",
        `Bạn đang xem CapyMedi với vai trò ${ROLE_LABELS[role].label}.`,
      );
      if (u.role === "patient" && u.profile_completed === false) {
        router.push("/onboarding/profile");
      } else {
        router.push(u.role === "doctor" ? "/doctor" : "/patient");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không vào được chế độ tham quan");
      setPending(null);
    }
  };

  const mobile = variant === "mobile";

  return (
    <div
      className={cn(
        "rounded-xl border border-dashed border-primary/40 bg-primary/5",
        mobile ? "mt-6 p-4" : "mt-5 p-4",
      )}
    >
      <p
        className={cn(
          "flex items-center gap-2 font-semibold text-foreground",
          mobile ? "text-base" : "text-sm",
        )}
      >
        <Compass className="h-4 w-4 shrink-0 text-primary" aria-hidden />
        Tham quan không cần tài khoản
      </p>
      <p className={cn("mt-1 text-muted-foreground", mobile ? "text-sm" : "text-xs")}>
        Chọn vai trò để vào ngay tài khoản dùng thử.
      </p>
      <div className={cn("mt-3 grid gap-2", roles.length > 1 && "grid-cols-2")}>
        {roles.map((role) => {
          const { label, icon: Icon } = ROLE_LABELS[role];
          return (
            <Button
              key={role}
              type="button"
              variant="outline"
              disabled={pending !== null}
              onClick={() => start(role)}
              className={cn(
                "w-full rounded-xl bg-card font-semibold",
                mobile ? "h-12 text-base" : "h-11",
              )}
            >
              <Icon aria-hidden />
              {pending === role ? "Đang vào..." : label}
            </Button>
          );
        })}
      </div>
      {error && <p className="mt-2 text-sm font-medium text-destructive">{error}</p>}
    </div>
  );
}
