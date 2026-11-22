"use client";

import { useEffect, useRef, useState } from "react";
import { Camera, Loader2, RotateCcw, SwitchCamera, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

function moTaLoi(err: unknown): string {
  const name = err instanceof DOMException ? err.name : "";
  if (name === "NotAllowedError") {
    return "Trình duyệt chưa được cấp quyền camera. Hãy cho phép truy cập camera rồi thử lại.";
  }
  if (name === "NotFoundError") {
    return "Không tìm thấy camera trên thiết bị này.";
  }
  return "Không mở được camera.";
}

// May co the cai webcam ao (Camo Studio, OBS Virtual Camera, Snap Camera,
// DroidCam...) - getUserMedia({video: true}) don gian de trinh duyet tu
// chon thiet bi mac dinh, co the roi dung vao webcam ao thay vi camera vat
// ly that. Nhan dien va tranh cac ten hay gap, chi lay deviceId that.
const WEBCAM_AO = /camo|obs|virtual|snap camera|manycam|droidcam|iriun|epoccam|elgato/i;

// Truoc day chi lay 1 deviceId (camera dau tien tim duoc) - tren dien thoai
// enumerateDevices() thuong tra camera TRUOC o vi tri dau, nen nguoi dung
// luon bi mo nham camera truoc, khong co cach doi sang camera sau (bat tien
// khi chup thuoc). Gio tra ca danh sach, uu tien camera co nhan "back"/
// "environment" len dau, de dialog mo dung camera sau mac dinh va cho doi
// camera trong danh sach con lai.
async function layDanhSachCameraThat(): Promise<MediaDeviceInfo[]> {
  // Nhan dang thiet bi (label) chi co sau khi da xin quyen it nhat 1 lan -
  // xin quyen tam bang constraint chung chung, dung ngay stream do, roi
  // enumerate lai de doc label that.
  const tam = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  tam.getTracks().forEach((t) => t.stop());

  const thietBi = await navigator.mediaDevices.enumerateDevices();
  const camera = thietBi.filter((d) => d.kind === "videoinput");
  const camThat = camera.filter((d) => !WEBCAM_AO.test(d.label));
  const danhSach = camThat.length > 0 ? camThat : camera;

  const camSau = danhSach.filter((d) => /back|environment|rear/i.test(d.label));
  const conLai = danhSach.filter((d) => !camSau.includes(d));
  return [...camSau, ...conLai];
}

export function CameraCapture({
  open,
  onOpenChange,
  onCapture,
  onFallbackToFile,
  title = "Chụp ảnh xác nhận",
  guidance = "Bày thuốc ra trước camera rồi bấm chụp.",
  review,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCapture: (file: File) => void;
  // getUserMedia can bi chan (quyen, khong co camera, trinh duyet khong ho
  // tro) - thay vi ket thuc bit tac, cho nguoi dung mot loi thoat sang chon
  // file thu cong. Bo qua khi co `review` (dialog tu mo chon file de anh tai
  // len cung di qua buoc xem truoc).
  onFallbackToFile?: () => void;
  title?: string;
  guidance?: string;
  // TASK-CAPY-27: co gia tri -> sau khi chup/tai len hien XEM TRUOC voi
  // "Chup lai" + nut gui (nhan `submitLabel`) + cau dong y `note` (vd "gui la
  // tu xac nhan da uong"). Khong co -> hanh vi cu (chup la gui ngay).
  review?: { submitLabel: string; note?: string };
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  // Danh sach camera that lay 1 lan moi khi mo dialog (khong enumerate lai
  // moi lan bam doi camera) - luu bang ref vi khong can render lai theo no,
  // chi can render lai theo soLuongCamera/viTriCamera.
  const danhSachCameraRef = useRef<MediaDeviceInfo[]>([]);
  const [dangMo, setDangMo] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  const [viTriCamera, setViTriCamera] = useState(0);
  const [soLuongCamera, setSoLuongCamera] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  // Anh cho xac nhan (buoc xem truoc) - chi dung khi co `review`.
  const [xemTruoc, setXemTruoc] = useState<{ file: File; url: string } | null>(null);

  useEffect(() => {
    if (!open) setXemTruoc(null);
  }, [open]);
  useEffect(
    () => () => {
      if (xemTruoc) URL.revokeObjectURL(xemTruoc.url);
    },
    [xemTruoc],
  );

  const nhanAnh = (file: File) => {
    if (!review) {
      onCapture(file);
      return;
    }
    setXemTruoc({ file, url: URL.createObjectURL(file) });
  };

  const dangXemTruoc = xemTruoc !== null;
  useEffect(() => {
    if (!open || dangXemTruoc) {
      if (dangXemTruoc) return;
      danhSachCameraRef.current = [];
      setViTriCamera(0);
      setSoLuongCamera(0);
      return;
    }
    setLoi(null);
    setDangMo(true);
    let huy = false;

    (async () => {
      if (danhSachCameraRef.current.length === 0) {
        danhSachCameraRef.current = await layDanhSachCameraThat();
        if (huy) return;
        setSoLuongCamera(danhSachCameraRef.current.length);
      }
      const danhSach = danhSachCameraRef.current;
      const deviceId = danhSach.length
        ? danhSach[viTriCamera % danhSach.length]?.deviceId
        : undefined;

      const stream = await navigator.mediaDevices.getUserMedia({
        video: deviceId ? { deviceId: { exact: deviceId } } : { facingMode: "environment" },
        audio: false,
      });
      if (huy) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      setDangMo(false);
    })().catch((err) => {
      if (huy) return;
      setDangMo(false);
      setLoi(moTaLoi(err));
    });

    return () => {
      huy = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, [open, viTriCamera, dangXemTruoc]);

  const doiCamera = () => {
    if (soLuongCamera < 2) return;
    setViTriCamera((v) => (v + 1) % soLuongCamera);
  };

  const chup = () => {
    const video = videoRef.current;
    if (!video || video.videoWidth === 0) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        nhanAnh(new File([blob], `dose-${Date.now()}.jpg`, { type: "image/jpeg" }));
      },
      "image/jpeg",
      0.9,
    );
  };

  const taiLen = () => {
    if (review) fileRef.current?.click();
    else {
      onOpenChange(false);
      onFallbackToFile?.();
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{xemTruoc ? "Xem lại ảnh" : title}</DialogTitle>
          <DialogDescription>{guidance}</DialogDescription>
        </DialogHeader>

        {review && (
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            data-testid="camera-file-input"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) nhanAnh(file);
            }}
          />
        )}

        {xemTruoc ? (
          <>
            <div className="relative aspect-video overflow-hidden rounded-xl bg-black">
              <img src={xemTruoc.url} alt="Ảnh vừa chụp" className="h-full w-full object-contain" />
            </div>
            {review?.note && (
              <p className="m-0 rounded-lg bg-[#F4F7FC] p-2.5 text-[12.5px] leading-[1.45] text-[#33456A]">
                {review.note}
              </p>
            )}
            <div className="flex flex-col gap-2">
              <Button className="w-full" size="lg" onClick={() => onCapture(xemTruoc.file)}>
                {review?.submitLabel}
              </Button>
              <Button className="w-full" variant="outline" onClick={() => setXemTruoc(null)}>
                <RotateCcw className="mr-1 h-4 w-4" /> Chụp lại
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="relative aspect-video overflow-hidden rounded-xl bg-black">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className={`h-full w-full object-cover ${dangMo || loi ? "invisible" : ""}`}
              />
              {dangMo && (
                <div className="absolute inset-0 flex items-center justify-center gap-2 text-sm text-white">
                  <Loader2 className="h-4 w-4 animate-spin" /> Đang mở camera…
                </div>
              )}
              {loi && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center text-sm text-white">
                  <p>{loi}</p>
                </div>
              )}
              {soLuongCamera > 1 && !loi && (
                <Button
                  type="button"
                  size="icon"
                  variant="secondary"
                  className="absolute right-2 top-2 rounded-full opacity-90"
                  disabled={dangMo}
                  onClick={doiCamera}
                  aria-label="Đổi camera"
                  title="Đổi camera"
                >
                  <SwitchCamera className="h-4 w-4" />
                </Button>
              )}
            </div>

            <div className="flex flex-col gap-2">
              {loi ? (
                <Button className="w-full" variant="outline" onClick={taiLen}>
                  <Upload className="mr-1 h-4 w-4" /> Tải ảnh lên thay thế
                </Button>
              ) : (
                <Button className="w-full" size="lg" disabled={dangMo} onClick={chup}>
                  <Camera className="mr-1 h-4 w-4" /> Chụp
                </Button>
              )}
              {review && (
                <div className="flex gap-2">
                  {!loi && (
                    <Button className="flex-1" variant="ghost" onClick={taiLen}>
                      <Upload className="mr-1 h-4 w-4" /> Tải ảnh lên
                    </Button>
                  )}
                  <Button className="flex-1" variant="ghost" onClick={() => onOpenChange(false)}>
                    <X className="mr-1 h-4 w-4" /> Huỷ
                  </Button>
                </div>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
