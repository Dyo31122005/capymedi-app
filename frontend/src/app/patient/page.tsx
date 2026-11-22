"use client";

// Tab "Hôm nay" - port tu capyphone.js::renderToday() + renderSheetNotYet()
// + renderFlowConfirm() + renderFlowSuccess(), noi voi du lieu lieu thuoc
// THAT qua lib/doses.
//
// Khac ban mau o cho: moi con so/chu deu tinh tu `doses` that, khong co
// MEDS hard-code, khong co "🔥 7 ngay lien tiep" (chua co gi tinh duoc
// chuoi ngay). Luong camera van dung CameraCapture + VLM that thay cho
// man hinh camera gia cua ban mau.

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Camera, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { CameraCapture } from "@/components/camera-capture";
import { MedicationImage } from "@/components/medication-image";
import {
  CHIP,
  CHIP_THEO_TRANG_THAI,
  CapyPrimaryButton,
  CapySecondaryButton,
  CapySheet,
  PillChip,
  SectionLabel,
  SheetRowButton,
  type ChipStyle,
} from "@/components/capy/capy-ui";
import {
  gioHienThi,
  listDoses,
  pollPhotoVerification,
  submitDosePhoto,
  updateDoseStatus,
  type Dose,
  type PhotoVerification,
  type PhotoVerificationDetail,
  type VerificationResult,
} from "@/lib/doses";
import { useAuth } from "@/lib/auth";
import { randomCapyQuote, type CapyQuote } from "@/lib/capy-quotes";
import { daNhac, danhDauDaNhac } from "@/lib/dose-reminder-log";
import { useProto } from "@/lib/proto-store";
import { postDailyCheckin } from "@/lib/rewards";
import { getCompanion, type CompanionState } from "@/lib/companion";
import {
  chonLoaiManHinh,
  daChoAn,
  danhDauDaChoAn,
  monAnTheoBuoi,
  type CapyFood,
} from "@/lib/care-moment";
import { CompanionCard } from "@/components/companion/companion-card";
import { CompanionSheet } from "@/components/companion/companion-sheet";
import { CareMoment } from "@/components/companion/care-moment";

// localStorage co the bi chan (private mode) - fedSlotIds chi la chong phat lai animation.
function khoTam(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

// GET /api/v1/doses tra ve TOAN BO lich (ke ca cac ngay tuong lai - moi don
// mac dinh sinh 7 ngay, xem SO_NGAY_MAC_DINH trong service.py), khong loc
// theo ngay. "Thoi khoa bieu hom nay" phai tu loc lai o day - so sanh theo
// ngay-thang cuc bo cua trinh duyet (may nguoi dung dat gio VN) chu khong
// phai ngay UTC, vi mot lieu 08:00 VN la 01:00 UTC hom sau/truoc bien gioi
// ngay UTC.
function laHomNay(iso: string): boolean {
  const d = new Date(iso);
  const nay = new Date();
  return (
    d.getFullYear() === nay.getFullYear() &&
    d.getMonth() === nay.getMonth() &&
    d.getDate() === nay.getDate()
  );
}

function tenThuoc(d: Dose): string {
  return d.expectedItems.map((i) => i.tenThuoc).join(", ") || "Thuốc";
}

function lieuLuong(d: Dose): string {
  return d.expectedItems.map((i) => `${i.soVien} ${i.dangThuoc ?? "đơn vị"}`).join(" · ");
}

function loiChao(ten: string): string {
  const h = new Date().getHours();
  const first = ten.trim().split(/\s+/).pop() ?? ten;
  if (h < 11) return `Chào buổi sáng, ${first} ☀️`;
  if (h < 13) return `Chào buổi trưa, ${first} 🌤️`;
  if (h < 18) return `Chào buổi chiều, ${first}`;
  return `Chào buổi tối, ${first} 🌙`;
}

// Vai manh phao hoa tinh (khong dung thu vien ngoai) - CSS keyframe
// `capyConfetti` dinh nghia o globals.css, cung mau voi capy-pop/capy-sheet.
const PHAO_HOA = [
  { emoji: "🎉", left: "8%", delay: "0s" },
  { emoji: "🎊", left: "20%", delay: "0.3s" },
  { emoji: "✨", left: "34%", delay: "0.1s" },
  { emoji: "🎈", left: "48%", delay: "0.5s" },
  { emoji: "🎉", left: "60%", delay: "0.2s" },
  { emoji: "✨", left: "72%", delay: "0.6s" },
  { emoji: "🎊", left: "84%", delay: "0.4s" },
  { emoji: "🎈", left: "92%", delay: "0s" },
];

type TrangThaiHero = "upcoming" | "due" | "waiting" | "overdue";

// TASK-CAPY-27 - cau chu luong chup anh xac nhan (PO 2026-11-14).
const HUONG_DAN_CHUP = "Chụp rõ tên thuốc, hàm lượng hoặc vỉ thuốc.";
// Nhan dien anh KHONG chung minh da uong: gui anh = benh nhan TU XAC NHAN da
// uong (backend chot TAKEN khi anh khop - ADR-0011), noi ro truoc khi gui.
const CAM_KET_GUI_ANH =
  "Khi gửi, bạn xác nhận mình đã uống liều này. Ảnh giúp kiểm tra đúng thuốc và số viên — ảnh không chứng minh bạn đã uống.";
const NHAN_KET_QUA_ANH: Record<VerificationResult, string> = {
  MATCHED: "Khớp đơn thuốc",
  MISMATCHED: "Chưa khớp đơn thuốc",
  UNCERTAIN: "Chưa chắc chắn",
};

// heroMap cua ban goc - giu nguyen mau nen, chip, nhan nut theo tung trang
// thai. Rieng `headline` dung ban "minimal" (khong co tranh Capy).
const HERO: Record<
  TrangThaiHero,
  { bg: string; chip: ChipStyle; headline: string; primary: string; secondary: string }
> = {
  upcoming: {
    bg: "#F4F7FC",
    chip: CHIP.upcoming,
    headline: "Liều tiếp theo",
    primary: "Chụp ảnh xác nhận",
    secondary: "Chưa uống",
  },
  due: {
    bg: "#CFE6FF",
    chip: CHIP.due,
    headline: "Đến giờ uống thuốc",
    primary: "Chụp ảnh xác nhận",
    secondary: "Chưa uống",
  },
  waiting: {
    bg: "#FDEBC9",
    chip: CHIP.waiting,
    headline: "Capy đang chờ xác nhận",
    primary: "Chụp ảnh xác nhận",
    secondary: "Nhắc lại sau",
  },
  overdue: {
    bg: "#FFD5C2",
    chip: CHIP.overdue,
    headline: "Capy chưa thấy bạn xác nhận",
    primary: "Chụp ảnh xác nhận",
    secondary: "Nhắc tôi sau",
  },
};

export default function PatientToday() {
  const router = useRouter();
  const { user, accessToken } = useAuth();
  const { requestSymptomCheck } = useProto();
  const patientId = user?.patient_id ?? "";

  const [doses, setDoses] = useState<Dose[]>([]);
  const [dangTai, setDangTai] = useState(true);

  const [xacMinh, setXacMinh] = useState<PhotoVerification | null>(null);
  const [dangGui, setDangGui] = useState(false);
  const [loiGui, setLoiGui] = useState<string | null>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  // "Chua uong" chi hoan giao dien - KHONG doi trang thai lieu that trong
  // DB (ADR-0011: chi bam nut moi tinh la bo qua).
  const [daHoan, setDaHoan] = useState<string | null>(null);
  const [sheet, setSheet] = useState<"notyet" | "confirm" | "huongdan" | "tuychon" | null>(null);
  const [dangXuLy, setDangXuLy] = useState(false);
  // Man hinh "Xong rồi!" sau khi anh khop - giu lai gio ghi nhan THAT va
  // ten thuoc cua lieu VUA xac nhan, vi sau khi tai lai `next` da nhay sang
  // lieu ke tiep (dung bug ma ban goc da ghi chu trong markNext()).
  const [thanhCong, setThanhCong] = useState<{
    at: string;
    line: string;
    pointsAwarded: number;
  } | null>(null);
  // Anh + quote Capy doi ngau nhien moi lan vao lai tab nay. Chon trong
  // useEffect chu khong phai luc render - xem ghi chu o randomCapyQuote().
  const [capy, setCapy] = useState<CapyQuote | null>(null);
  // Khao sat "ban co khoe khong" sau khi het lieu trong ngay - thay cho luong
  // ghi nhat ky thu cong cu (bo o health/page.tsx, xem lib/escalations.ts).
  // Khoa theo NGAY hien tai (localStorage qua lib/dose-reminder-log, tai su
  // dung dung ham "da nhac" da co san thay vi tu viet lai) - moi ngay hoi lai
  // 1 lan, tra loi roi thi khong hoi nua du con vao lai trang.
  const [daTraLoiKhaoSat, setDaTraLoiKhaoSat] = useState(true);
  const [mungRo, setMungRo] = useState(false);
  // Capybara Companion (ADR-0016). null = chua tai / loi -> giao dien cu y nguyen.
  const [companion, setCompanion] = useState<CompanionState | null>(null);
  const [moCapy, setMoCapy] = useState(false);
  const [capyTick, setCapyTick] = useState(0);
  const [moment, setMoment] = useState<{
    kind: "FEED" | "SUPPORTIVE" | "GROWTH";
    food?: CapyFood;
    infoLine?: string;
    pointsAwarded?: number;
    awaitingCaregiver?: boolean;
    doseId?: string;
  } | null>(null);
  const capyBat = companion?.enabled ? companion : null;
  const [diemKhaoSat, setDiemKhaoSat] = useState(0);
  const khoaKhaoSat = `khao-sat-suc-khoe:${new Date().toDateString()}`;

  useEffect(() => {
    setCapy(randomCapyQuote());
    setDaTraLoiKhaoSat(daNhac(khoaKhaoSat));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const traLoiKhaoSat = (on: boolean) => {
    danhDauDaNhac(khoaKhaoSat);
    setDaTraLoiKhaoSat(true);
    // Ghi nhan de cong diem thuong. KHONG await: benh nhan tra loi "Khong
    // on" phai duoc dieu huong sang Capy AI ngay, khong doi mang. Backend tu
    // chan cong trung trong ngay nen goi lai khong sinh diem ao.
    postDailyCheckin(on, accessToken).then((ketQua) => {
      // Chi hien diem khi con o man hinh mung ro (tra loi "On") - nhanh
      // "Khong on" da dieu huong sang Capy AI ngay ben duoi, khong ai
      // con thay state nay nua.
      if (ketQua && ketQua.pointsAwarded > 0) setDiemKhaoSat(ketQua.pointsAwarded);
    });
    if (on) {
      setMungRo(true);
    } else {
      // requestSymptomCheck() bao trang Capy AI tu mo loi hoi trieu chung
      // ngay khi vao (xem effect trong patient/assistant/page.tsx) - ha tang
      // nay da co san tu truoc, chi chua noi dau goi nao toi no.
      requestSymptomCheck();
      router.push("/patient/assistant");
    }
  };

  const taiLaiDoses = async (): Promise<Dose[] | null> => {
    if (!patientId) return null;
    setDangTai(true);
    try {
      const moi = await listDoses(patientId);
      setDoses(moi);
      return moi;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không tải được lịch uống thuốc");
      return null;
    } finally {
      setDangTai(false);
    }
  };

  // Tien do Capy LUON lay tu backend. Loi/tat -> giu giao dien cu.
  useEffect(() => {
    if (!accessToken) return;
    getCompanion(accessToken)
      .then((c) => {
        setCompanion(c);
        // Capy da lon trong luc vang mat (vd nguoi than duyet) va chua xem le.
        if (c.enabled && c.pendingCelebrationStage != null)
          setMoment((m) => m ?? { kind: "GROWTH" });
      })
      .catch(() => setCompanion(null));
  }, [accessToken]);

  /** Mo man Capy sau xac nhan; tra ve true neu da mo (thay cho UI cu). */
  const moManCapy = (
    kq: Parameters<typeof chonLoaiManHinh>[0],
    dose: Dose,
    extra: {
      infoLine?: string;
      pointsAwarded?: number;
    },
  ): boolean => {
    if (!capyBat) return false;
    const loai = chonLoaiManHinh(kq);
    if (loai === "FEED") {
      if (daChoAn(dose.id, kq.now, khoTam())) return false;
      danhDauDaChoAn(dose.id, kq.now, khoTam());
      setMoment({ kind: "FEED", food: monAnTheoBuoi(dose.scheduledAt), ...extra });
      return true;
    }
    if (loai === "SUPPORTIVE") {
      setMoment({
        kind: "SUPPORTIVE",
        awaitingCaregiver: kq.resultStatus === "AWAITING_CAREGIVER",
        doseId: dose.id,
      });
      return true;
    }
    return false;
  };

  // Lay lai tien do THAT tu backend (vd sau khi dong man Capy truoc khi co ket
  // qua, hoac xac nhan khong mo man Capy) - the khong bao gio giu so cu.
  const taiLaiCapy = () => {
    if (!accessToken || !capyBat) return;
    getCompanion(accessToken)
      .then((c) => {
        if (!c.enabled) return setCompanion(c);
        if (c.stage > capyBat.stage || c.progressPct > capyBat.progressPct)
          setCapyTick((n) => n + 1);
        setCompanion(c);
      })
      .catch(() => undefined);
  };

  const dongManCapy = (latest: CompanionState | null) => {
    setMoment(null);
    if (!latest) {
      taiLaiCapy();
      return;
    }
    if (latest.enabled) {
      if (capyBat && (latest.stage > capyBat.stage || latest.progressPct > capyBat.progressPct)) {
        setCapyTick((n) => n + 1);
      }
      setCompanion(latest);
    }
  };

  useEffect(() => {
    taiLaiDoses();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId]);

  const dosesHomNay = doses.filter((d) => laHomNay(d.scheduledAt));
  const next = dosesHomNay.find((d) => d.status === "PENDING");
  const daXong = dosesHomNay.filter((d) => d.status !== "PENDING").length;
  // Anh khong khop sau 3 lan chup: dose chuyen AWAITING_CAREGIVER (xem
  // verifier.py), KHONG phai da uong xong - phai tach rieng khoi tatCaXong
  // de khong hien nham man hinh "Xong het roi! 🎉".
  const choDuyet = dosesHomNay.filter((d) => d.status === "AWAITING_CAREGIVER");
  const tatCaXong = dosesHomNay.length > 0 && !next && choDuyet.length === 0;
  // Khao sat suc khoe hoi duoc khi khong con gi phai lam trong ngay - KE CA
  // benh nhan khong co don thuoc nao (truoc day `tatCaXong` doi
  // dosesHomNay.length > 0 nen nhom nay khong bao gio duoc hoi, va cung
  // khong co cach nao tich diem). Tach bien rieng thay vi noi long
  // `tatCaXong`: khoi "Xong het roi 🎉" ben duoi VAN phai doi co lieu that,
  // khong the chuc mung nguoi chua uong gi.
  const duocKhaoSat = tatCaXong || dosesHomNay.length === 0;
  // `xacMinh` la ket qua cua lan chup GAN NHAT, khong tu xoa khi `next` nhay
  // sang lieu khac (vd lieu vua chup het 3 lan -> AWAITING_CAREGIVER, hero
  // card chuyen sang lieu ke tiep) - neu dung thang `xacMinh` o duoi, canh
  // bao "da chup du 3 lan" cua lieu CU se hien nham len lieu MOI chua he
  // dung toi. Chi dung ket qua khi no thuoc dung ve lieu dang hien thi.
  const xacMinhChoLieuNay = xacMinh?.doseEventId === next?.id ? xacMinh : null;
  const lieuMai = doses
    .filter((d) => d.status === "PENDING" && !laHomNay(d.scheduledAt))
    .sort((a, b) => a.scheduledAt.localeCompare(b.scheduledAt))[0];

  const trangThai: TrangThaiHero = (() => {
    if (!next) return "due";
    if (daHoan === next.id) return "waiting";
    const now = Date.now();
    if (now < new Date(next.windowStart).getTime()) return "upcoming";
    if (now > new Date(next.windowEnd).getTime()) return "overdue";
    return "due";
  })();
  const hero = HERO[trangThai];
  // THEM (migration 0052) - benh nhan tu tat yeu cau chup anh trong Cai dat
  // (xem components/account-settings.tsx). Khi tat, MOI lieu duoc coi la
  // "khong can anh" (giong lieu qua gio/da hoan) bat ke khung gio - nut
  // chinh luon la "Toi da uong"/"Chua uong", khong bao gio mo camera.
  //
  // TASK-CAPY-27 (khoi phuc luong chup anh truoc): truoc day lieu QUA GIO hoac
  // DA HOAN cung bi coi la "khong can anh" -> nut chinh thanh "Toi da uong",
  // camera bien mat dung luc benh nhan hay xac nhan nhat. Gio camera luon la
  // nut chinh khi benh nhan chua tat chup anh; tu bao khong anh nam trong
  // "Tuy chon khac". Giu ton trong cai dat tat chup anh cua benh nhan.
  const chupAnhBat = user?.photo_capture_enabled ?? true;
  const khongCanAnh = !chupAnhBat;

  const cuaSo = (() => {
    if (!next) return "";
    if (trangThai === "waiting") return "đã hoãn • Capy vẫn đang chờ bạn xác nhận";
    if (trangThai === "overdue") {
      const phut = Math.round((Date.now() - new Date(next.windowEnd).getTime()) / 60000);
      return `quá giờ hẹn ${phut} phút • giờ xác nhận thật sẽ được ghi`;
    }
    const hauTo = chupAnhBat ? " • cần ảnh" : "";
    return `khung xác nhận: ${gioHienThi(next.windowStart)} – ${gioHienThi(next.windowEnd)}${hauTo}`;
  })();

  const gioSau = (phut: number) =>
    new Date(Date.now() + phut * 60000).toLocaleTimeString("vi-VN", {
      timeZone: "Asia/Ho_Chi_Minh",
      hour: "2-digit",
      minute: "2-digit",
    });

  const guiAnh = async (doseId: string, file: File) => {
    const lieu = doses.find((d) => d.id === doseId);
    setDangGui(true);
    setLoiGui(null);
    setXacMinh(null);
    try {
      const daGui = await submitDosePhoto(doseId, file);
      setXacMinh(daGui);
      const ketQua = await pollPhotoVerification(daGui.id, setXacMinh);
      setXacMinh(ketQua);

      // Soan san noi dung man hinh thanh cong, nhung CHI hien sau khi da
      // tai lai danh sach lieu: dong dem "X / Y lieu hom nay" trong do doc
      // tu `doses`, ma luc nay lieu vua xac nhan van con PENDING - hien
      // ngay se ra so cu (vd "1 / 2" thay vi "2 / 2") trong vai tram ms.
      const xong = ketQua.matched
        ? {
            at: gioHienThi(ketQua.createdAt),
            line: lieu
              ? `${tenThuoc(lieu)} · ${lieuLuong(lieu)} • hẹn ${gioHienThi(lieu.scheduledAt)}`
              : "",
            pointsAwarded: ketQua.pointsAwarded ?? 0,
          }
        : null;

      if (ketQua.matched && ketQua.verification?.ocrConflict) {
        // Quyet dinh da duyet (ADR-0011) giu nguyen, nhung KHONG im lang: chu
        // tren nhan (OCR) khac don o truong co y nghia lam sang.
        toast.warning(
          `Lưu ý: chữ trên nhãn khác đơn thuốc (${ketQua.verification.ocrVlmConflicts
            .map((f) => (f === "strength" ? "hàm lượng" : f === "form" ? "dạng thuốc" : f))
            .join(", ")}). Bạn hoặc người thân nên kiểm tra lại.`,
        );
      }

      if (!ketQua.matched) {
        if (ketQua.nextAction === "CAREGIVER_REVIEW") {
          toast.error("Đã hết lượt chụp lại — chuyển người thân xem giúp");
        } else if (ketQua.status === "loi_he_thong") {
          // Cau THAT tu backend (vd "AI dem thuoc chua duoc bat..."), khong gan cung.
          toast.error(ketQua.message);
        } else if (ketQua.status === "do_tin_cay_thap") {
          // Anh chua du ro de Capy chac chan (khong tinh vao han muc chup
          // lai, xem backend/services/photo_verification/verifier.py) - mo
          // luon sheet huong dan chup anh da co san thay vi chi toast chung
          // chung, giup benh nhan sua dung cho lan sau.
          toast(ketQua.message);
          setSheet("huongdan");
        } else {
          toast(ketQua.message);
        }
      }

      const dsMoi = await taiLaiDoses();
      // Trang thai THAT cua lieu sau xac minh do backend tra ve (khong suy tu HTTP 200).
      const lieuMoi = dsMoi?.find((d) => d.id === doseId);
      const daMoCapy =
        lieuMoi != null &&
        moManCapy(
          {
            source: "PHOTO",
            resultStatus: lieuMoi.status,
            scheduledAt: lieuMoi.scheduledAt,
            now: new Date(),
            matched: ketQua.matched,
            nextAction: ketQua.nextAction,
          },
          lieuMoi,
          {
            infoLine: xong ? `Ghi nhận lúc ${xong.at} · ${xong.line}` : undefined,
            pointsAwarded: xong?.pointsAwarded,
          },
        );
      if (xong && !daMoCapy) setThanhCong(xong);
      if (!daMoCapy) taiLaiCapy();
    } catch (err) {
      setLoiGui(err instanceof Error ? err.message : "Không gửi được ảnh");
    } finally {
      setDangGui(false);
    }
  };

  // Tu bao "da uong" KHONG kem anh - mo duoc khi tat chup anh trong Cai dat,
  // hoac lieu da qua gio/da hoan (xem `khongCanAnh`).
  //
  // SUA 2026-08-28: truoc day chuyen sang AWAITING_CAREGIVER de cho nguoi than
  // duyet. Nhung benh nhan KHONG co nguoi than thi ket vinh vien o do - khong
  // job nao quet trang thai nay, va no cung nam ngoai vong nhac lai (chi lay
  // status "PENDING", xem backend/services/dose_push_reminder.py). Gio chap
  // nhan loi tu khai va chot ngay, danh doi bang diem thap hon (-50%, tinh o
  // backend/api/dose_routes.py::_xac_dinh_ty_le_thuong).
  const xacNhanKhongAnh = async () => {
    if (!next) return;
    setDangXuLy(true);
    try {
      const lieuMoi = await updateDoseStatus(next.id, "TAKEN", accessToken);
      setSheet(null);
      const daMoCapy = moManCapy(
        {
          source: "SELF_REPORT",
          resultStatus: lieuMoi.status,
          scheduledAt: lieuMoi.scheduledAt,
          now: new Date(),
        },
        lieuMoi,
        { pointsAwarded: lieuMoi.pointsAwarded },
      );
      if (!daMoCapy) {
        toast.success("Đã ghi nhận bạn uống thuốc. Cảm ơn bạn!");
        taiLaiCapy();
      }
      await taiLaiDoses();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không gửi được yêu cầu xác nhận");
    } finally {
      setDangXuLy(false);
    }
  };

  const boQuaLieu = async () => {
    if (!next) return;
    setDangXuLy(true);
    try {
      await updateDoseStatus(next.id, "MISSED", accessToken);
      toast("Đã ghi nhận bỏ qua liều này");
      setSheet(null);
      await taiLaiDoses();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không ghi được");
    } finally {
      setDangXuLy(false);
    }
  };

  const hoanNhac = () => {
    if (!next) return;
    setDaHoan(next.id);
    setSheet(null);
    toast("Đã hoãn nhắc — liều này vẫn chưa bị tính là bỏ qua");
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Loi chao + tieu de */}
      {user && !dangTai && (
        <div>
          <p className="m-0 text-[13px] font-medium tracking-[.02em] text-[#5B6A85]">
            {loiChao(user.full_name)}
          </p>
          <h1 className="font-display m-0 mt-0.5 text-[30px] font-extrabold leading-[1.1] text-[#16386E]">
            {next ? hero.headline : tatCaXong ? "Hết liều cho hôm nay" : "Hôm nay"}
          </h1>
        </div>
      )}

      {/* Khoi Capy (ban "capyFull" cua thiet ke goc) - anh + quote ngau
          nhien, doi moi lan vao lai tab nay. */}
      {capyBat && (
        <CompanionCard
          companion={capyBat}
          dosesHomNay={dosesHomNay}
          onOpen={() => setMoCapy(true)}
          paused={moment != null || moCapy}
          progressTick={capyTick}
        />
      )}
      {!capyBat && capy && (
        <div className="flex items-center gap-3.5 rounded-[28px] bg-[#CFE6FF] p-4">
          <Image
            src={capy.src}
            alt={capy.alt}
            width={110}
            height={110}
            className="h-[110px] w-[110px] shrink-0 rounded-[24px] object-contain"
            priority
          />
          <div className="min-w-0">
            <p className="font-display m-0 text-[15px] font-bold leading-[1.35] text-[#16386E]">
              {capy.line}
            </p>
            <p className="m-0 mt-1.5 text-[12px] leading-[1.45] text-[#3D5D8C]">{capy.sub}</p>
          </div>
        </div>
      )}

      {dangTai && (
        <div className="flex items-center justify-center gap-2 rounded-[22px] bg-white p-6 text-sm text-[#5B6A85]">
          <Loader2 className="h-4 w-4 animate-spin" /> Đang tải lịch uống thuốc…
        </div>
      )}

      {/* The lieu chinh */}
      {!dangTai && next && (
        <div className="overflow-hidden rounded-[30px] bg-white shadow-[0_10px_30px_rgba(22,56,110,.07)]">
          <div className="px-5 pb-[18px] pt-5" style={{ background: hero.bg }}>
            <PillChip chip={hero.chip} />
            <p className="font-display m-0 mt-3 text-[46px] font-extrabold leading-none tracking-[-.01em] text-[#16386E]">
              {gioHienThi(next.scheduledAt)}
            </p>
            <p className="font-display m-0 mt-2 text-[20px] font-bold leading-[1.25] text-[#16386E]">
              {tenThuoc(next)}
            </p>
            <p className="m-0 mt-0.5 text-[14px] font-semibold text-[#2F5488]">{lieuLuong(next)}</p>
            <div className="mt-3 flex flex-wrap gap-2" aria-label="Hình ảnh thuốc trong liều này">
              {next.expectedItems.map((item) => (
                <MedicationImage
                  key={`${next.id}:${item.drugId}:${item.drugProductId ?? "unmapped"}`}
                  image={item.image}
                  accessToken={accessToken}
                  drugName={item.tenThuoc}
                  size="md"
                />
              ))}
            </div>
            {cuaSo && <p className="font-mono m-0 mt-2.5 text-[11px] text-[#5B7098]">{cuaSo}</p>}
          </div>

          <div className="flex flex-col gap-2.5 p-4">
            {dangGui && (
              <div className="flex items-center gap-3 rounded-[16px] bg-[#CFE6FF] p-3 text-sm text-[#16386E]">
                <Loader2 className="h-5 w-5 shrink-0 animate-spin" />
                <span>
                  {xacMinhChoLieuNay?.message ??
                    "Đang phân tích ảnh, việc này có thể mất vài phút — bạn cứ để yên máy."}
                  {xacMinhChoLieuNay && xacMinhChoLieuNay.attempt > 0 && (
                    <span className="block text-xs opacity-75">
                      Lần {xacMinhChoLieuNay.attempt}/{xacMinhChoLieuNay.maxAttempts}
                    </span>
                  )}
                </span>
              </div>
            )}

            {!dangGui &&
              xacMinhChoLieuNay &&
              !xacMinhChoLieuNay.matched &&
              xacMinhChoLieuNay.status !== "dang_xu_ly" && (
                <div
                  className="rounded-[16px] p-3 text-sm"
                  style={
                    xacMinhChoLieuNay.nextAction === "CAREGIVER_REVIEW"
                      ? { background: "#FDEBC9", color: "#8A6516" }
                      : { background: "#F6E1DD", color: "#B4432C" }
                  }
                >
                  {xacMinhChoLieuNay.verification && (
                    <span className="mb-0.5 block text-[11.5px] font-bold uppercase tracking-[.04em] opacity-80">
                      {NHAN_KET_QUA_ANH[xacMinhChoLieuNay.verification.verificationResult]}
                    </span>
                  )}
                  {xacMinhChoLieuNay.message}
                  {xacMinhChoLieuNay.verification && (
                    <ChiTietXacMinh v={xacMinhChoLieuNay.verification} />
                  )}
                </div>
              )}

            {loiGui && (
              <div className="rounded-[16px] bg-[#F6E1DD] p-3 text-sm text-[#B4432C]">{loiGui}</div>
            )}

            {chupAnhBat && !dangGui && (
              <p className="m-0 text-center text-[12.5px] leading-[1.45] text-[#5B6A85]">
                {HUONG_DAN_CHUP}
              </p>
            )}

            <CapyPrimaryButton
              disabled={dangGui}
              onClick={chupAnhBat ? () => setCameraOpen(true) : () => setSheet("confirm")}
            >
              {dangGui ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  {!khongCanAnh && <Camera className="h-4 w-4" />}
                  {(() => {
                    if (xacMinhChoLieuNay?.nextAction === "RETAKE" && chupAnhBat) return "Chụp lại";
                    // chupAnhBat=false: nhan luon phai la "Toi da uong", du
                    // hero.primary (theo trangThai upcoming/due) noi "Chụp &
                    // xác nhận" - nut o day khong bao gio mo camera nua.
                    return chupAnhBat ? "Chụp ảnh xác nhận" : "Tôi đã uống";
                  })()}
                </>
              )}
            </CapyPrimaryButton>

            <div className="flex gap-2.5">
              <CapySecondaryButton disabled={dangGui} onClick={() => setSheet("notyet")}>
                {hero.secondary}
              </CapySecondaryButton>
              {chupAnhBat && (
                <CapySecondaryButton disabled={dangGui} onClick={() => setSheet("tuychon")}>
                  Tùy chọn khác
                </CapySecondaryButton>
              )}
            </div>
          </div>
        </div>
      )}

      <CameraCapture
        open={cameraOpen}
        onOpenChange={setCameraOpen}
        guidance={`${HUONG_DAN_CHUP} Bày đủ số viên của liều này trong khung hình.`}
        review={{ submitLabel: "Gửi ảnh & xác nhận đã uống", note: CAM_KET_GUI_ANH }}
        onCapture={(file) => {
          setCameraOpen(false);
          if (next) guiAnh(next.id, file);
        }}
      />

      {/* Xong het trong ngay */}
      {!dangTai && tatCaXong && (
        <div className="capy-pop rounded-[30px] bg-[#BFEBDC] px-5 py-[22px] text-center">
          <p className="font-display m-0 text-[26px] font-extrabold leading-[1.15] text-[#14563F]">
            Xong hết rồi! 🎉
          </p>
          <p className="m-0 mt-1.5 text-[14px] leading-[1.5] text-[#1F6A50]">
            Bạn đã hoàn thành tất cả {dosesHomNay.length} liều hôm nay.
            {lieuMai && ` Liều tiếp theo: ${gioHienThi(lieuMai.scheduledAt)} ngày mai.`}
          </p>
          <button
            onClick={() => router.push("/patient/history")}
            className="font-display mt-4 flex min-h-[52px] w-full items-center justify-center rounded-[20px] bg-[#16386E] text-[16px] font-bold text-white transition-colors hover:bg-[#0E2749]"
          >
            Xem tiến độ
          </button>
        </div>
      )}

      {/* Khao sat suc khoe - chi hien khi da xong het lieu hom nay VA chua
          tra loi khao sat cua hom nay. */}
      {!dangTai && duocKhaoSat && !daTraLoiKhaoSat && (
        <div className="capy-pop rounded-[30px] bg-white p-5 text-center shadow-[0_10px_30px_rgba(22,56,110,.07)]">
          <p className="font-display m-0 text-[19px] font-bold text-[#16386E]">
            Hôm nay bạn cảm thấy thế nào?
          </p>
          <p className="m-0 mt-1 text-[13px] leading-[1.5] text-[#5B6A85]">
            {dosesHomNay.length === 0
              ? "Hôm nay bạn không có liều nào, Capy hỏi thăm bạn một chút."
              : "Đã uống hết thuốc rồi, Capy hỏi thăm bạn một chút."}
          </p>
          <div className="mt-4 flex gap-2.5">
            <CapySecondaryButton className="flex-1" onClick={() => traLoiKhaoSat(false)}>
              Không ổn 😕
            </CapySecondaryButton>
            <CapyPrimaryButton className="flex-1" onClick={() => traLoiKhaoSat(true)}>
              Ổn 🙂
            </CapyPrimaryButton>
          </div>
        </div>
      )}

      {!dangTai && dosesHomNay.length === 0 && (
        <div className="rounded-[22px] bg-white p-6 text-center text-sm text-[#5B6A85]">
          Hôm nay bạn không có liều thuốc nào.
        </div>
      )}

      {/* Thoi khoa bieu */}
      {dosesHomNay.length > 0 && (
        <div>
          <div className="mb-2.5 mt-2">
            <SectionLabel>Thời khoá biểu hôm nay</SectionLabel>
          </div>
          <div className="flex flex-col gap-2.5">
            {dosesHomNay.map((d) => {
              const chip =
                d.id === next?.id ? hero.chip : (CHIP_THEO_TRANG_THAI[d.status] ?? CHIP.upcoming);
              return (
                <div
                  key={d.id}
                  className="grid grid-cols-[52px_auto_minmax(0,1fr)_auto] items-center gap-3 rounded-[22px] bg-white px-4 py-3.5"
                >
                  <span className="font-display text-[15px] font-bold text-[#16386E]">
                    {gioHienThi(d.scheduledAt)}
                  </span>
                  <span className="flex -space-x-2" aria-label={`Hình ảnh thuốc: ${tenThuoc(d)}`}>
                    {d.expectedItems.map((item) => (
                      <MedicationImage
                        key={`${d.id}:${item.drugId}:${item.drugProductId ?? "unmapped"}`}
                        image={item.image}
                        accessToken={accessToken}
                        drugName={item.tenThuoc}
                        size="sm"
                      />
                    ))}
                  </span>
                  <span className="block min-w-0">
                    <span
                      className="block truncate text-[14px] font-semibold text-[#1B2A44]"
                      title={`${gioHienThi(d.scheduledAt)} · ${tenThuoc(d)}`}
                    >
                      {tenThuoc(d)}
                    </span>
                    <span className="block text-[12px] text-[#62708A]">{lieuLuong(d)}</span>
                  </span>
                  <PillChip chip={chip} />
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Sheet "Tùy chọn khác" (TASK-CAPY-27) - moi duong KHONG chup anh gom
          vao day, de camera la duong xac nhan chinh. */}
      {sheet === "tuychon" && next && (
        <CapySheet onClose={() => setSheet(null)}>
          <p className="font-display m-0 text-[22px] font-extrabold leading-[1.2] text-[#16386E]">
            Tùy chọn khác
          </p>
          <div className="mt-[18px] flex flex-col gap-2.5">
            <SheetRowButton
              label="Tôi không thể chụp ảnh — xác nhận thủ công"
              onClick={() => setSheet("confirm")}
            />
            <SheetRowButton label="Xem hướng dẫn chụp ảnh" onClick={() => setSheet("huongdan")} />
          </div>
        </CapySheet>
      )}

      {/* Sheet "Chưa uống được lúc này?" */}
      {sheet === "notyet" && next && (
        <CapySheet onClose={() => setSheet(null)}>
          <p className="font-display m-0 text-[22px] font-extrabold leading-[1.2] text-[#16386E]">
            Chưa uống được lúc này?
          </p>
          <p className="m-0 mt-1.5 text-[13.5px] leading-[1.5] text-[#5B6A85]">
            Liều này vẫn chưa bị tính là bỏ qua.
          </p>
          <div className="mt-[18px] flex flex-col gap-2.5">
            <SheetRowButton label="Nhắc lại sau 10 phút" meta={gioSau(10)} onClick={hoanNhac} />
            <SheetRowButton label="Nhắc lại sau 30 phút" meta={gioSau(30)} onClick={hoanNhac} />
            <SheetRowButton label="Chọn thời gian khác" onClick={() => setSheet(null)} />
            <button
              onClick={boQuaLieu}
              disabled={dangXuLy}
              className="flex min-h-[48px] items-center justify-center rounded-[16px] text-[14px] font-semibold text-[#B4432C] transition-colors hover:bg-[#FBF1EF] disabled:opacity-50"
            >
              Bỏ qua liều này
            </button>
          </div>
        </CapySheet>
      )}

      {/* Sheet xác nhận không cần ảnh */}
      {sheet === "confirm" && next && (
        <CapySheet onClose={() => setSheet(null)}>
          <p className="font-display m-0 text-[24px] font-extrabold leading-[1.2] text-[#16386E]">
            Bạn đã uống liều này chưa?
          </p>
          <div className="mt-3.5 rounded-[20px] bg-[#F4F7FC] p-4">
            <p className="font-display m-0 text-[17px] font-bold text-[#16386E]">
              {tenThuoc(next)} · {lieuLuong(next)}
            </p>
            <p className="m-0 mt-0.5 text-[12.5px] text-[#5B6A85]">
              Hẹn {gioHienThi(next.scheduledAt)} • chưa có ảnh xác nhận
            </p>
          </div>
          <div className="mt-[18px] flex flex-col gap-2.5">
            <CapyPrimaryButton
              disabled={dangXuLy}
              onClick={xacNhanKhongAnh}
              className="min-h-[58px]"
            >
              {dangXuLy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Tôi đã uống ✓"}
            </CapyPrimaryButton>
            <CapySecondaryButton
              disabled={dangXuLy}
              onClick={() => setSheet(null)}
              className="min-h-[50px]"
            >
              Chưa uống
            </CapySecondaryButton>
          </div>
          <p className="font-mono m-0 mt-3.5 text-center text-[11px] leading-[1.5] text-[#5B6A85]">
            Bạn tự xác nhận không kèm ảnh, nên điểm thưởng của liều này sẽ thấp hơn một chút.
          </p>
        </CapySheet>
      )}

      {/* Sheet huong dan chup anh - THAY vi nhay sang /patient/assistant nhu
          truoc (bug bao cao 2026-08-20: bam "Xem huong dan" tu dung sang
          chatbot, khong lien quan). Noi dung tinh, khong goi API nao. */}
      {sheet === "huongdan" && (
        <CapySheet onClose={() => setSheet(null)}>
          <p className="font-display m-0 text-[22px] font-extrabold leading-[1.2] text-[#16386E]">
            Chụp sao cho Capy nhìn rõ nhé
          </p>
          <p className="m-0 mt-1.5 text-[13.5px] leading-[1.5] text-[#5B6A85]">
            Vài mẹo nhỏ để ảnh rõ nét, khỏi phải chụp lại cho mệt.
          </p>
          <div className="mt-[18px] flex flex-col gap-2.5">
            {[
              {
                icon: "💡",
                title: "Chụp nơi đủ sáng",
                desc: "Bật đèn phòng hoặc ra chỗ sáng, tránh chụp ngược sáng cửa sổ.",
              },
              {
                icon: "🍽️",
                title: "Đặt thuốc trên nền trơn",
                desc: "Một cái đĩa hay tờ giấy trắng là đủ, đừng để lẫn vào đồ khác trên bàn.",
              },
              {
                icon: "🔍",
                title: "Lại gần một chút",
                desc: "Để thuốc chiếm phần lớn khung hình, sao cho đếm được rõ từng viên.",
              },
              {
                icon: "🤲",
                title: "Đừng che mất thuốc",
                desc: "Bỏ tay, hộp thuốc hay vật khác ra khỏi khung hình trước khi chụp.",
              },
            ].map((m) => (
              <div
                key={m.title}
                className="flex items-start gap-3 rounded-[18px] bg-[#F4F7FC] p-3.5"
              >
                <span className="text-[22px] leading-none">{m.icon}</span>
                <span className="min-w-0">
                  <span className="font-display block text-[14px] font-bold text-[#16386E]">
                    {m.title}
                  </span>
                  <span className="mt-0.5 block text-[12.5px] leading-[1.45] text-[#5B6A85]">
                    {m.desc}
                  </span>
                </span>
              </div>
            ))}
          </div>
          <div className="mt-[18px] flex flex-col gap-2.5">
            <CapyPrimaryButton
              className="min-h-[54px]"
              onClick={() => {
                setSheet(null);
                setCameraOpen(true);
              }}
            >
              Đã rõ, chụp ảnh thôi
            </CapyPrimaryButton>
            <CapySecondaryButton onClick={() => setSheet(null)}>Đóng</CapySecondaryButton>
          </div>
        </CapySheet>
      )}

      {/* Capybara Companion: cho an / ho tro / le lon len (ADR-0016). */}
      {moment && capyBat && (
        <CareMoment
          kind={moment.kind}
          companion={capyBat}
          food={moment.food}
          infoLine={moment.infoLine}
          pointsAwarded={moment.pointsAwarded}
          awaitingCaregiver={moment.awaitingCaregiver}
          accessToken={accessToken}
          onClose={dongManCapy}
          onExplicitConfirm={
            moment.kind === "SUPPORTIVE" && !moment.awaitingCaregiver && moment.doseId
              ? async () => {
                  // Xac nhan ro rang (tu khai) cho lieu fallback - backend ghi audit,
                  // KHONG doi status/LP; Capy chi lon tu day (QA-03).
                  try {
                    const lieuMoi = await updateDoseStatus(moment.doseId!, "TAKEN", accessToken);
                    setMoment(null);
                    const daMo = moManCapy(
                      {
                        source: "SELF_REPORT",
                        resultStatus: lieuMoi.status,
                        scheduledAt: lieuMoi.scheduledAt,
                        now: new Date(),
                      },
                      lieuMoi,
                      {},
                    );
                    if (!daMo) taiLaiCapy();
                  } catch (err) {
                    toast.error(err instanceof Error ? err.message : "Không gửi được xác nhận");
                  }
                }
              : undefined
          }
        />
      )}
      {moCapy && capyBat && !moment && (
        <CompanionSheet
          companion={capyBat}
          accessToken={accessToken}
          onClose={() => setMoCapy(false)}
          onUpdated={setCompanion}
        />
      )}

      {/* Màn hình thành công sau khi ảnh khớp */}
      {thanhCong && (
        <div className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-[#BFEBDC] p-8 text-center">
          <p className="font-display m-0 text-[30px] font-extrabold leading-[1.15] text-[#14563F]">
            Xong rồi!
          </p>
          <p className="m-0 mt-2 text-[15px] font-medium leading-[1.5] text-[#1F6A50]">
            Capy ghi nhận lúc <strong>{thanhCong.at}</strong> ✨
          </p>
          <p className="m-0 mt-1.5 text-[12.5px] text-[#2F6A54]">{thanhCong.line}</p>
          {thanhCong.pointsAwarded > 0 && (
            <p className="font-display m-0 mt-2 text-[15px] font-extrabold text-[#14563F]">
              +{thanhCong.pointsAwarded} điểm
            </p>
          )}
          <p className="font-mono m-0 mt-1 text-[12px] text-[#2F6A54]">
            {daXong} / {dosesHomNay.length} liều hôm nay
          </p>
          <button
            onClick={() => setThanhCong(null)}
            className="font-display mt-[26px] flex min-h-[56px] min-w-[200px] items-center justify-center rounded-[20px] bg-[#16386E] text-[17px] font-bold text-white transition-colors hover:bg-[#0E2749]"
          >
            Về Hôm nay
          </button>
        </div>
      )}

      {/* An mung khi tra loi "On" o khao sat suc khoe - phao hoa tinh bang
          CSS (keyframe capyConfetti trong globals.css), khong can thu vien
          ngoai. */}
      {mungRo && (
        <div className="absolute inset-0 z-50 flex flex-col items-center justify-center overflow-hidden bg-[#BFEBDC] p-8 text-center">
          <div aria-hidden="true" className="pointer-events-none absolute inset-0">
            {PHAO_HOA.map((p, i) => (
              <span
                key={i}
                className="capy-confetti absolute text-[26px]"
                style={{ left: p.left, animationDelay: p.delay }}
              >
                {p.emoji}
              </span>
            ))}
          </div>
          <p className="font-display m-0 text-[30px] font-extrabold leading-[1.15] text-[#14563F]">
            Tuyệt vời! 🎉
          </p>
          <p className="m-0 mt-2 text-[15px] font-medium leading-[1.5] text-[#1F6A50]">
            Cảm ơn bạn đã chia sẻ. Chúc bạn một ngày khoẻ mạnh!
          </p>
          {diemKhaoSat > 0 && (
            <p className="font-display m-0 mt-2 text-[15px] font-extrabold text-[#14563F]">
              +{diemKhaoSat} điểm
            </p>
          )}
          <button
            onClick={() => {
              setMungRo(false);
              setDiemKhaoSat(0);
            }}
            className="font-display relative mt-[26px] flex min-h-[56px] min-w-[200px] items-center justify-center rounded-[20px] bg-[#16386E] text-[17px] font-bold text-white transition-colors hover:bg-[#0E2749]"
          >
            Về Hôm nay
          </button>
        </div>
      )}
    </div>
  );
}

// Audit 2026-11-14: tach ro 3 nguon - OCR THAT, AI dem thuoc (VLM) THAT, doi
// chieu don - de khong trinh bay ket qua nhu "AI da xac minh" khi VLM chua chay.
function ChiTietXacMinh({ v }: { v: PhotoVerificationDetail }) {
  const ocr = (() => {
    if (!v.ocrStatus || v.ocrStatus === "OCR_NOT_RUN") return "chưa bật";
    if (v.ocrStatus !== "OCR_AVAILABLE") return "không chạy được";
    const e = v.extracted;
    if (v.nameStatus === "FOUND" && e.name)
      return `đọc được ${e.name}${e.strength ? ` · ${e.strength} ${e.unit ?? ""}` : ""}`;
    if (e.strength) return `đọc được hàm lượng ${e.strength} ${e.unit ?? ""}, chưa thấy tên thuốc`;
    return "chưa đọc rõ chữ trên thuốc";
  })();
  const vlm =
    v.vlmStatus === "OK"
      ? "đã chạy"
      : v.vlmStatus === "UNAVAILABLE"
        ? "chưa được bật trên máy chủ"
        : v.vlmStatus === "ERROR"
          ? "lỗi khi gọi"
          : "không chạy";
  return (
    <span className="mt-1.5 block text-[11.5px] leading-[1.5] opacity-80">
      Đọc chữ (OCR): {ocr}
      <br />
      AI đếm thuốc: {vlm}
    </span>
  );
}
